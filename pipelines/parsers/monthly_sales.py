"""
Pipeline 1: Monthly Sales by Branch
Extracts: branch, month, year, date, revenue, is_partial_history

NOTE — Use for trend / momentum / volatility / branch demand index.
       Do NOT use for seasonality (only 4-5 months per branch).
       This is the branch-level revenue source of truth.
"""

import re
import pandas as pd
from .utils import (
    read_lines, parse_csv_line, parse_number,
    is_noise, is_date_line, is_total_line, looks_like_standalone_label,
)

SIGNATURE = "monthly sales"

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

_BRANCH_PREFIX = re.compile(r"^Branch\s*Name\s*:\s*", re.IGNORECASE)
_COL_HEADER_RE = re.compile(r"^Month\s*,", re.IGNORECASE)


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

        # Branch header: "Branch Name: <name>"
        m = _BRANCH_PREFIX.match(first)
        if m:
            current_branch = first[m.end():].strip()
            continue

        # Skip totals
        if is_total_line(raw):
            continue

        # Skip standalone labels (report-level header like "Conut - Tyre,,,,")
        if looks_like_standalone_label(cells):
            continue

        # Data row: month,,year,total — month in [0], year in [2], total in [3]
        if current_branch and len(cells) >= 4:
            month_name = first
            year_val = parse_number(cells[2])
            revenue = parse_number(cells[3])

            if month_name.lower() in _MONTHS and year_val and revenue is not None:
                records.append({
                    "branch": current_branch,
                    "month": month_name,
                    "year": int(year_val),
                    "revenue": revenue,
                })

    df = pd.DataFrame(records)
    if not df.empty:
        df["month_num"] = df["month"].str.lower().map(_MONTHS)
        df["date"] = pd.to_datetime(
            df.apply(lambda r: f"{r['year']}-{r['month_num']:02d}-01", axis=1)
        )
        df = df.sort_values(["branch", "date"]).reset_index(drop=True)

        # Flag branches with fewer months than the maximum observed
        max_months = df.groupby("branch").size().max()
        branch_counts = df.groupby("branch").size()
        df["is_partial_history"] = df["branch"].map(
            lambda b: branch_counts[b] < max_months
        )
    return df
