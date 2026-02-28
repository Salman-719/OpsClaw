"""
Pipeline 4: Customer Orders (Delivery)
Extracts: branch, customer, phone, first_order, last_order, total, num_orders,
          is_zero_value_customer, recency_days, customer_lifespan_days,
          avg_order_value, is_repeat_customer

NOTE — `phone` is the canonical customer key (for repeat/retention analysis).
       `Person_XXXX` is only an anonymized label.
       Do NOT use this as a time-series source (no per-order timestamps).
       Use for: recency, frequency, spend tier, repeat rate, active span.
"""

import re
import pandas as pd
from .utils import (
    read_lines, parse_number,
    is_noise, is_page_break, is_copyright,
)

SIGNATURE = "customer orders"

_PERSON_RE = re.compile(r"(Person_\d+)")
_DATETIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})")
_QUOTED_NUM_RE = re.compile(r'"([\d,]+\.?\d*)"')
_COL_HEADER_RE = re.compile(r"Customer Name\s*,\s*Address", re.IGNORECASE)
_TOTAL_BRANCH_RE = re.compile(r"Total By Branch", re.IGNORECASE)
_BRANCH_NAME_RE = re.compile(r"^[A-Z][A-Za-z\s\-'']+$")


def can_parse(lines: list[str]) -> bool:
    return SIGNATURE in " ".join(lines[:5]).lower()


def parse(filepath: str) -> pd.DataFrame:
    lines = read_lines(filepath)
    records = []
    current_branch = None

    for line in lines:
        raw = line.strip()
        if is_noise(raw):
            continue
        if _COL_HEADER_RE.match(raw):
            continue
        if "customer orders" in raw.lower() or "from date:" in raw.lower():
            continue

        # Branch total → skip but don't reset branch
        if _TOTAL_BRANCH_RE.search(raw):
            continue

        # Standalone branch header: text in first cell, rest empty
        cells = raw.split(",")
        first = cells[0].strip()
        rest_empty = all(c.strip() == "" for c in cells[1:])

        if rest_empty and first and _BRANCH_NAME_RE.match(first) and not _PERSON_RE.search(first):
            current_branch = first
            continue

        # Data row: contains Person_XXXX
        person_match = _PERSON_RE.search(raw)
        if person_match and current_branch:
            customer = person_match.group(1)

            # Extract dates
            dates = _DATETIME_RE.findall(raw)
            first_order = dates[0] if dates else None
            last_order = dates[1] if len(dates) > 1 else first_order

            # Extract phone: digits near person name
            phone = ""
            phone_match = re.search(r"Person_\d+\s*,\s*[^,]*,\s*(\d[\d\s]*)", raw)
            if phone_match:
                phone = phone_match.group(1).strip()

            # Extract total: largest quoted number or 0.00
            total = 0.0
            quoted = _QUOTED_NUM_RE.findall(raw)
            if quoted:
                total = parse_number(quoted[0]) or 0.0
            elif ",0.00," in raw:
                total = 0.0

            # Extract order count: small int after total
            num_orders = 1
            small_ints = re.findall(r",\s*(\d{1,3})\s*,", raw)
            for n in reversed(small_ints):
                v = int(n)
                if 1 <= v <= 500:
                    num_orders = v
                    break

            records.append({
                "branch": current_branch,
                "customer": customer,
                "phone": phone,
                "first_order": first_order,
                "last_order": last_order,
                "total": total,
                "num_orders": num_orders,
            })

    df = pd.DataFrame(records)
    if not df.empty:
        for col in ("first_order", "last_order"):
            df[col] = pd.to_datetime(df[col], format="%Y-%m-%d %H:%M", errors="coerce")

        # Renamed: "is_cancelled" → "is_zero_value_customer" (could be refund, test, void)
        df["is_zero_value_customer"] = df["total"] == 0.0

        # Derived fields
        reference_date = df["last_order"].max()
        df["recency_days"] = (reference_date - df["last_order"]).dt.days
        df["customer_lifespan_days"] = (df["last_order"] - df["first_order"]).dt.days
        df["avg_order_value"] = (df["total"] / df["num_orders"].replace(0, 1)).round(2)
        df["is_repeat_customer"] = df["num_orders"] > 1

        df = df.sort_values(["branch", "last_order"], ascending=[True, False]).reset_index(drop=True)
    return df
