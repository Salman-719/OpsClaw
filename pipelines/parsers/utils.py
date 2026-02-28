"""
Common utilities for parsing Omega POS report-style CSV exports.

All detection is pattern-based, not value-based:
  - Branch headers: detected by context (text + rest empty), not by hardcoded names
  - Data rows: detected by numeric cell shape
  - Page breaks: "Page X of Y" anywhere in line
  - Totals: line starts with "Total"
  - Numbers: stripped of quotes/commas, validated as float
"""

import re
import csv
import io
from typing import Optional


# ─── Number parsing ───────────────────────────────────────────────────────────

_NUM_RE = re.compile(r"^-?[\d,]+\.?\d*$")


def parse_number(value: str) -> Optional[float]:
    """Parse a number that may have commas, quotes, or whitespace. Returns None on failure."""
    if value is None:
        return None
    cleaned = value.strip().replace('"', "").replace(",", "").strip()
    if not cleaned or cleaned == "-":
        return None
    if _NUM_RE.match(cleaned):
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


# ─── Line classification ─────────────────────────────────────────────────────

_PAGE_RE = re.compile(r"Page\s+\d+\s+of", re.IGNORECASE)
_DATE_LINE_RE = re.compile(r"^\d{2}-\w{3}-\d{2}")
_COPYRIGHT_RE = re.compile(r"Copyright|www\.omegapos|All Rights Reserved|^REP_S_\d+,", re.IGNORECASE)
_TOTAL_RE = re.compile(r"^\s*,?\s*Total", re.IGNORECASE)


def is_page_break(line: str) -> bool:
    return bool(_PAGE_RE.search(line))


def is_date_line(line: str) -> bool:
    return bool(_DATE_LINE_RE.match(line.strip()))


def is_copyright(line: str) -> bool:
    return bool(_COPYRIGHT_RE.search(line))


def is_total_line(line: str) -> bool:
    return bool(_TOTAL_RE.match(line))


def is_blank(line: str) -> bool:
    return len(line.strip().replace(",", "").strip()) == 0


def is_noise(line: str) -> bool:
    """True if the line is any kind of report chrome (not data)."""
    return is_page_break(line) or is_copyright(line) or is_blank(line)


# ─── CSV line parsing ─────────────────────────────────────────────────────────

def parse_csv_line(line: str) -> list[str]:
    """Parse a single CSV line respecting quoted fields."""
    reader = csv.reader(io.StringIO(line))
    for row in reader:
        return [cell.strip() for cell in row]
    return []


# ─── File reading ─────────────────────────────────────────────────────────────

def read_lines(filepath: str) -> list[str]:
    """Read all lines, trying multiple encodings."""
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(filepath, "r", encoding=enc) as f:
                return f.readlines()
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {filepath}")


# ─── Header detection ─────────────────────────────────────────────────────────

def looks_like_standalone_label(cells: list[str]) -> bool:
    """True if first cell has text and the rest are empty — typical branch/section header."""
    if not cells or not cells[0]:
        return False
    non_empty = [c for c in cells[1:] if c]
    return len(non_empty) == 0


def detect_report_type(lines: list[str]) -> Optional[str]:
    """Auto-detect report type from first 5 lines. Returns a key or None."""
    header = " ".join(lines[:5]).lower()
    signatures = {
        "monthly sales": "monthly_sales",
        "sales by items by group": "items_by_group",
        "average sales by menu": "avg_sales_menu",
        "customer orders (delivery)": "customer_orders",
        "sales by customer in details": "transaction_baskets",
        "time & attendance": "attendance",
    }
    for sig, key in signatures.items():
        if sig in header:
            return key
    return None
