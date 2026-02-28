"""
cleaning.py
===========
Feature 3 – Expansion Feasibility  |  Data Ingestion & Cleaning Layer

Provides one top-level function per data source plus a combined loader
`load_all_sources(data_dir)` that returns a dict of cleaned DataFrames.

Each parser is hardened against the Omega POS report-style artefacts:
  - Repeated column-header rows
  - Page-break / date-watermark rows
  - Copyright footer rows
  - Blank / comma-only rows
  - Quoted numbers with thousands separators
  - Inconsistent branch-name strings

OUTPUT SCHEMAS
--------------
monthly_sales  : branch(str), branch_raw(str), month(str), month_num(int),
                 year(int), revenue(float)

customer_orders: branch(str), branch_raw(str), customer(str),
                 total(float), num_orders(int), avg_order_value(float)

tax_summary    : branch(str), branch_raw(str), vat(float), total_tax(float)

attendance     : branch(str), branch_raw(str), emp_id(str), duration_hours(float)

delivery_detail: branch(str), branch_raw(str), customer(str),
                 item(str), qty(float), price(float)
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Optional

import pandas as pd

from .utils import get_logger, normalise_branch, parse_number, parse_duration_hms

logger = get_logger("feature_3.cleaning")

# ──────────────────────────────────────────────────────────────────────────────
# SHARED LOW-LEVEL HELPERS
# ──────────────────────────────────────────────────────────────────────────────

_PAGE_RE      = re.compile(r"Page\s+\d+\s+of", re.IGNORECASE)
_DATE_LINE_RE = re.compile(r"^\d{2}-\w{3}-\d{2}")
_COPYRIGHT_RE = re.compile(r"Copyright|omegapos|All Rights Reserved|^REP_S_\d+", re.IGNORECASE)
_TOTAL_RE     = re.compile(r"^\s*,?\s*Total", re.IGNORECASE)
_MONTHS       = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _read_lines(filepath: str | Path) -> list[str]:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(filepath, "r", encoding=enc, errors="replace") as fh:
                return fh.readlines()
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {filepath}")


def _parse_csv_line(line: str) -> list[str]:
    reader = csv.reader(io.StringIO(line))
    for row in reader:
        return [c.strip() for c in row]
    return []


def _is_noise(line: str) -> bool:
    s = line.strip()
    if not s or not s.replace(",", "").strip():
        return True
    if _PAGE_RE.search(s):
        return True
    if _COPYRIGHT_RE.search(s):
        return True
    return False


def _is_total(line: str) -> bool:
    return bool(_TOTAL_RE.match(line.strip()))


def _is_date_watermark(line: str) -> bool:
    return bool(_DATE_LINE_RE.match(line.strip()))


def _attach_branch(records: list[dict], branch_raw: str) -> None:
    """Mutate the last appended record to attach branch info (helper)."""
    pass  # used inline below


# ──────────────────────────────────────────────────────────────────────────────
# 1. MONTHLY SALES BY BRANCH  (rep_s_00334_1_SMRY / monthly_sales_by_branch.csv)
# ──────────────────────────────────────────────────────────────────────────────

_MONTHLY_BRANCH_RE = re.compile(r"^Branch\s*Name\s*:\s*(.+)", re.IGNORECASE)
_MONTHLY_COL_RE    = re.compile(r"^Month\s*,", re.IGNORECASE)


def parse_monthly_sales(filepath: str | Path) -> pd.DataFrame:
    """
    Parse the Omega POS monthly-sales-by-branch report.

    Returns columns: branch, branch_raw, month, month_num, year, revenue
    """
    lines = _read_lines(filepath)
    records: list[dict] = []
    current_branch_raw: Optional[str] = None

    for line in lines:
        if _is_noise(line) or _is_date_watermark(line) or _is_total(line):
            continue
        raw = line.strip()
        if _MONTHLY_COL_RE.match(raw):   # skip column header rows
            continue

        cells = _parse_csv_line(raw)
        if not cells:
            continue

        # Branch header
        m = _MONTHLY_BRANCH_RE.match(cells[0])
        if m:
            current_branch_raw = m.group(1).strip()
            continue

        # Data row: Month,,Year,Total,
        if current_branch_raw and len(cells) >= 4:
            month_name = cells[0].strip()
            year_val   = parse_number(cells[2])
            revenue    = parse_number(cells[3])
            if month_name.lower() in _MONTHS and year_val is not None and revenue is not None:
                records.append({
                    "branch_raw": current_branch_raw,
                    "branch":     normalise_branch(current_branch_raw),
                    "month":      month_name,
                    "month_num":  _MONTHS[month_name.lower()],
                    "year":       int(year_val),
                    "revenue":    revenue,
                })

    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("monthly_sales: parsed 0 rows from %s", filepath)
        return df
    df = df[df["branch"].notna()].copy()
    logger.info("monthly_sales: %d rows, branches: %s", len(df), df["branch"].unique().tolist())
    return df


# ──────────────────────────────────────────────────────────────────────────────
# 2. CUSTOMER ORDERS  (rep_s_00150 / customer_orders_delivery.csv)
# ──────────────────────────────────────────────────────────────────────────────

_PERSON_RE        = re.compile(r"^(Person_\d+)$", re.IGNORECASE)
_COL_HEADER_CU_RE = re.compile(r"Customer Name\s*,", re.IGNORECASE)
_BRANCH_TOTAL_RE  = re.compile(r"Total By Branch", re.IGNORECASE)
_BRANCH_LABEL_RE  = re.compile(r"^[A-Za-z][A-Za-z0-9\s\-'()]+$")


def parse_customer_orders(filepath: str | Path) -> pd.DataFrame:
    """
    Parse the Omega POS customer orders (delivery) report.

    Returns columns: branch, branch_raw, customer, total, num_orders, avg_order_value
    """
    lines = _read_lines(filepath)
    records: list[dict] = []
    current_branch_raw: Optional[str] = None

    i = 0
    while i < len(lines):
        line = lines[i]
        if _is_noise(line):
            i += 1
            continue
        raw = line.strip()

        if _COL_HEADER_CU_RE.match(raw) or "customer orders" in raw.lower() or "from date:" in raw.lower():
            i += 1
            continue
        if _BRANCH_TOTAL_RE.search(raw):
            i += 1
            continue
        if _is_total(raw):
            i += 1
            continue

        cells = _parse_csv_line(raw)
        if not cells:
            i += 1
            continue

        first = cells[0].strip()
        rest_empty = all(c.strip() == "" for c in cells[1:])

        # Standalone branch label line
        if rest_empty and first and _BRANCH_LABEL_RE.match(first) and not _PERSON_RE.match(first):
            norm = normalise_branch(first)
            if norm:
                current_branch_raw = first
            i += 1
            continue

        # The customer-orders report is tricky: rows bleed across lines.
        # Strategy: look for a Person_XXXX token – accumulate the logical row
        # by concatenating lines until we have enough numeric tokens.
        if current_branch_raw and _PERSON_RE.match(first):
            # Collect full logical record (sometimes wraps to next line)
            logical = raw
            j = i + 1
            while j < len(lines) and j < i + 4:
                nxt = lines[j].strip()
                if not nxt or _PERSON_RE.match(nxt) or _is_noise(lines[j]):
                    break
                logical += "," + nxt
                j += 1
            logical_cells = _parse_csv_line(logical)
            # Extract numbers
            nums = [parse_number(c) for c in logical_cells if parse_number(c) is not None]
            if len(nums) >= 2:
                total      = nums[-2] if len(nums) >= 2 else None
                num_orders = int(nums[-1]) if nums[-1] is not None else None
                if total is not None and num_orders is not None and num_orders > 0:
                    records.append({
                        "branch_raw":      current_branch_raw,
                        "branch":          normalise_branch(current_branch_raw),
                        "customer":        first,
                        "total":           total,
                        "num_orders":      num_orders,
                        "avg_order_value": total / num_orders,
                    })
            i = j
            continue

        i += 1

    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("customer_orders: parsed 0 rows from %s", filepath)
        return df
    df = df[df["branch"].notna() & (df["total"] > 0)].copy()
    logger.info("customer_orders: %d rows, branches: %s", len(df), df["branch"].unique().tolist())
    return df


# ──────────────────────────────────────────────────────────────────────────────
# 3. TAX SUMMARY BY BRANCH  (REP_S_00194_SMRY / tax_summary_by_branch.csv)
# ──────────────────────────────────────────────────────────────────────────────

_TAX_BRANCH_RE     = re.compile(r"^Branch\s*Name\s*:\s*(.+)", re.IGNORECASE)
_TAX_TOTAL_LINE_RE = re.compile(r"Total By Branch", re.IGNORECASE)


def parse_tax_summary(filepath: str | Path) -> pd.DataFrame:
    """
    Parse the Omega POS tax-summary-by-branch report.

    Returns columns: branch, branch_raw, vat, total_tax
    """
    lines = _read_lines(filepath)
    records: list[dict] = []
    current_branch_raw: Optional[str] = None

    for line in lines:
        if _is_noise(line) or _is_date_watermark(line):
            continue
        raw = line.strip()
        if "tax report" in raw.lower() or "tax description" in raw.lower() or "vat" in raw.lower()[:20]:
            continue

        cells = _parse_csv_line(raw)
        if not cells:
            continue

        # Branch header
        bm = _TAX_BRANCH_RE.match(cells[0])
        if bm:
            current_branch_raw = bm.group(1).strip()
            continue

        # Total row: "Total By Branch","<vat>",0.00,...,"<total>"
        if current_branch_raw and _TAX_TOTAL_LINE_RE.search(raw):
            nums = [parse_number(c) for c in cells if parse_number(c) is not None]
            if nums:
                vat   = nums[0]
                total = nums[-1]
                records.append({
                    "branch_raw": current_branch_raw,
                    "branch":     normalise_branch(current_branch_raw),
                    "vat":        vat,
                    "total_tax":  total,
                })

    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("tax_summary: parsed 0 rows from %s", filepath)
        return df
    df = df[df["branch"].notna()].copy()
    logger.info("tax_summary: %d rows, branches: %s", len(df), df["branch"].unique().tolist())
    return df


# ──────────────────────────────────────────────────────────────────────────────
# 4. TIME & ATTENDANCE  (REP_S_00461 / time_and_attendance_logs.csv)
# ──────────────────────────────────────────────────────────────────────────────

_ATT_EMP_RE      = re.compile(r"EMP ID\s*:\s*([\d.]+)")
_ATT_NAME_RE     = re.compile(r"NAME\s*:\s*(Person_\d+)")
_ATT_DURATION_RE = re.compile(r"(\d{2}[.:]\d{2}[.:]\d{2})\s*$")
_ATT_BRANCH_RE   = re.compile(r"^[A-Za-z][A-Za-z0-9\s\-'()]+$")


def parse_attendance(filepath: str | Path) -> pd.DataFrame:
    """
    Parse the Omega POS time-and-attendance report.

    Returns columns: branch, branch_raw, emp_id, duration_hours
    """
    lines = _read_lines(filepath)
    records: list[dict] = []
    emp_id: Optional[str] = None
    current_branch_raw: Optional[str] = None
    awaiting_branch = False

    for line in lines:
        if _is_noise(line):
            continue
        raw = line.strip()

        if "time & attendance" in raw.lower() or "punch in" in raw.lower() or "from date:" in raw.lower():
            continue

        # Employee header line
        em = _ATT_EMP_RE.search(raw)
        nm = _ATT_NAME_RE.search(raw)
        if em or nm:
            emp_id = em.group(1).strip() if em else emp_id
            awaiting_branch = True
            continue

        # After an emp header, first non-noise line contains the branch name
        if awaiting_branch:
            cells = _parse_csv_line(raw)
            for c in cells:
                if c and _ATT_BRANCH_RE.match(c):
                    norm = normalise_branch(c)
                    if norm:
                        current_branch_raw = c
                    break
            awaiting_branch = False
            continue

        # Duration line: ends with HH.MM.SS
        dm = _ATT_DURATION_RE.search(raw)
        if dm and emp_id and current_branch_raw:
            dur = parse_duration_hms(dm.group(1))
            if dur is not None and dur > 0.1:   # ignore clock-glitches < 6 min
                records.append({
                    "branch_raw":     current_branch_raw,
                    "branch":         normalise_branch(current_branch_raw),
                    "emp_id":         emp_id,
                    "duration_hours": dur,
                })

    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("attendance: parsed 0 rows from %s", filepath)
        return df
    df = df[df["branch"].notna() & (df["duration_hours"] > 0)].copy()
    logger.info("attendance: %d rows, branches: %s", len(df), df["branch"].unique().tolist())
    return df


# ──────────────────────────────────────────────────────────────────────────────
# 5. DELIVERY DETAIL  (REP_S_00502 / sales_by_customer_detail_delivery.csv)
# ──────────────────────────────────────────────────────────────────────────────

_DELIV_BRANCH_RE  = re.compile(r"^Branch\s*[:\s]\s*(.+)", re.IGNORECASE)
_DELIV_PERSON_RE  = re.compile(r"^(Person_\d+)")
_DELIV_COL_RE     = re.compile(r"^Full Name\s*,", re.IGNORECASE)


def parse_delivery_detail(filepath: str | Path) -> pd.DataFrame:
    """
    Parse the delivery-channel line-item detail report (REP_S_00502).

    Returns columns: branch, branch_raw, customer, item, qty, price
    Used mainly to infer delivery_share (fraction of orders coming via delivery).
    """
    lines = _read_lines(filepath)
    records: list[dict] = []
    current_branch_raw: Optional[str] = None
    current_customer: Optional[str] = None

    for line in lines:
        if _is_noise(line) or _is_date_watermark(line) or _is_total(line):
            continue
        raw = line.strip()
        if _DELIV_COL_RE.match(raw) or "sales by customer" in raw.lower() or "from date:" in raw.lower():
            continue

        cells = _parse_csv_line(raw)
        if not cells:
            continue

        first = cells[0].strip()

        # Branch header
        bm = _DELIV_BRANCH_RE.match(first)
        if bm:
            current_branch_raw = bm.group(1).strip()
            current_customer   = None
            continue

        # Customer name
        if _DELIV_PERSON_RE.match(first):
            current_customer = first
            continue

        # Item row: first cell empty, qty in [1], item in [2], price in [3]
        if current_branch_raw and current_customer and not first:
            try:
                qty   = parse_number(cells[1]) if len(cells) > 1 else None
                item  = cells[2].strip()         if len(cells) > 2 else ""
                price = parse_number(cells[3])   if len(cells) > 3 else None
            except IndexError:
                continue
            if item and qty and qty > 0 and price is not None and price > 0:
                records.append({
                    "branch_raw": current_branch_raw,
                    "branch":     normalise_branch(current_branch_raw),
                    "customer":   current_customer,
                    "item":       item,
                    "qty":        qty,
                    "price":      price,
                })

    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("delivery_detail: parsed 0 rows from %s", filepath)
        return df
    df = df[df["branch"].notna()].copy()
    logger.info("delivery_detail: %d rows, branches: %s", len(df), df["branch"].unique().tolist())
    return df


# ──────────────────────────────────────────────────────────────────────────────
# COMBINED LOADER
# ──────────────────────────────────────────────────────────────────────────────

# Map of known filenames (lowercase) to their parser
_FILE_PARSERS = {
    "monthly_sales_by_branch.csv":              parse_monthly_sales,
    "rep_s_00334_1_smry.csv":                   parse_monthly_sales,
    "customer_orders_delivery.csv":             parse_customer_orders,
    "rep_s_00150.csv":                          parse_customer_orders,
    "tax_summary_by_branch.csv":                parse_tax_summary,
    "rep_s_00194_smry.csv":                     parse_tax_summary,
    "time_and_attendance_logs.csv":             parse_attendance,
    "rep_s_00461.csv":                          parse_attendance,
    "sales_by_customer_detail_delivery.csv":    parse_delivery_detail,
    "rep_s_00502.csv":                          parse_delivery_detail,
}


def load_all_sources(data_dir: str | Path) -> dict[str, pd.DataFrame]:
    """
    Discover and parse all known source files in `data_dir`.

    Returns a dict with keys:
      "monthly_sales", "customer_orders", "tax_summary",
      "attendance", "delivery_detail"
    Missing files are silently absent from the dict (callers must handle).
    """
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise FileNotFoundError(f"data_dir not found: {data_dir}")

    results: dict[str, pd.DataFrame] = {}
    key_map = {
        "monthly_sales_by_branch.csv":           "monthly_sales",
        "rep_s_00334_1_smry.csv":                "monthly_sales",
        "customer_orders_delivery.csv":          "customer_orders",
        "rep_s_00150.csv":                       "customer_orders",
        "tax_summary_by_branch.csv":             "tax_summary",
        "rep_s_00194_smry.csv":                  "tax_summary",
        "time_and_attendance_logs.csv":          "attendance",
        "rep_s_00461.csv":                       "attendance",
        "sales_by_customer_detail_delivery.csv": "delivery_detail",
        "rep_s_00502.csv":                       "delivery_detail",
    }

    for fpath in data_dir.iterdir():
        fname_lower = fpath.name.lower()
        parser = _FILE_PARSERS.get(fname_lower)
        key    = key_map.get(fname_lower)
        if parser and key:
            if key not in results:   # first match wins
                logger.info("Loading %s → key '%s'", fpath.name, key)
                try:
                    results[key] = parser(fpath)
                except Exception as exc:
                    logger.error("Failed to parse %s: %s", fpath.name, exc)

    loaded = list(results.keys())
    logger.info("load_all_sources: loaded keys: %s", loaded)
    return results
