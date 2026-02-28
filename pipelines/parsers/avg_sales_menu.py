"""
Pipeline 3: Average Sales by Menu (Channel KPIs)
Extracts: branch, channel, customers, sales, avg_per_customer,
          sales_share_within_branch, customer_share_within_branch

NOTE — Treat as a branch-channel aggregate, not a time series.
       Strong for: branch archetyping, channel dependence, avg ticket, promo targeting.
"""

import re
import pandas as pd
from .utils import (
    read_lines, parse_csv_line, parse_number,
    is_noise, is_date_line, is_total_line, looks_like_standalone_label,
)

SIGNATURE = "average sales by menu"

_COL_HEADER_RE = re.compile(r"^Menu Name\s*,", re.IGNORECASE)
_KNOWN_CHANNELS = re.compile(r"^(DELIVERY|TABLE|TAKE\s*AWAY)$", re.IGNORECASE)


def can_parse(lines: list[str]) -> bool:
    return SIGNATURE in " ".join(lines[:5]).lower()


def parse(filepath: str) -> pd.DataFrame:
    lines = read_lines(filepath)
    records = []
    current_branch = None

    for line in lines:
        raw = line.strip()
        if is_noise(raw) or is_date_line(raw):
            continue
        if _COL_HEADER_RE.match(raw):
            continue

        cells = parse_csv_line(raw)
        if not cells:
            continue

        first = cells[0]

        # Skip report title
        if "average sales" in first.lower() or "year:" in raw.lower():
            continue

        # Skip totals
        if is_total_line(raw):
            continue

        # Standalone label → branch header
        if looks_like_standalone_label(cells) and first:
            current_branch = first
            continue

        # Data row: channel, #cust, sales, avg
        if current_branch and _KNOWN_CHANNELS.match(first) and len(cells) >= 4:
            customers = parse_number(cells[1])
            sales = parse_number(cells[2])
            avg = parse_number(cells[3])

            if customers is not None and sales is not None:
                records.append({
                    "branch": current_branch,
                    "channel": first.upper(),
                    "customers": customers,
                    "sales": sales,
                    "avg_per_customer": avg if avg else (sales / customers if customers > 0 else 0),
                })

    df = pd.DataFrame(records)
    if not df.empty:
        branch_sales = df.groupby("branch")["sales"].transform("sum")
        branch_cust = df.groupby("branch")["customers"].transform("sum")
        df["sales_share_within_branch"] = (df["sales"] / branch_sales.replace(0, 1)).round(6)
        df["customer_share_within_branch"] = (df["customers"] / branch_cust.replace(0, 1)).round(6)
    return df
