"""
Pipeline 2: Sales by Items and Groups
Extracts: branch, division, group, item, qty, amount, is_modifier, category,
          item_sales_share_within_branch, item_rank_within_branch, item_rank_within_division

NOTE — Treat as product-MIX data (ranking, share, category importance).
       Not for branch-level revenue truth (use monthly_sales for that).
"""

import re
import pandas as pd
from .utils import (
    read_lines, parse_csv_line, parse_number,
    is_noise, is_date_line, is_total_line, looks_like_standalone_label,
)

SIGNATURE = "sales by items by group"

_PREFIX_RE = {
    "branch": re.compile(r"^Branch\s*:\s*", re.IGNORECASE),
    "division": re.compile(r"^Division\s*:\s*", re.IGNORECASE),
    "group": re.compile(r"^Group\s*:\s*", re.IGNORECASE),
}
_COL_HEADER_RE = re.compile(r"^Description\s*,\s*Barcode", re.IGNORECASE)

# Category tagging — richer layer for cross-sell / upsell modeling
_COFFEE_HOT_PATTERN = re.compile(r"hot.?coffee", re.IGNORECASE)
_COFFEE_COLD_PATTERN = re.compile(r"frappes?|iced.?coffee|cold.?brew", re.IGNORECASE)
_SHAKE_PATTERN = re.compile(r"shakes?|milkshakes?", re.IGNORECASE)
_BEVERAGE_PATTERN = re.compile(r"juice|lemonade|tea|smoothie|drink|mojito", re.IGNORECASE)


def can_parse(lines: list[str]) -> bool:
    return SIGNATURE in " ".join(lines[:5]).lower()


def parse(filepath: str) -> pd.DataFrame:
    lines = read_lines(filepath)
    records = []
    branch = division = group = None

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

        # Hierarchy headers
        for key, pat in _PREFIX_RE.items():
            m = pat.match(first)
            if m:
                val = first[m.end():].strip()
                if key == "branch":
                    branch, division, group = val, None, None
                elif key == "division":
                    division, group = val, None
                elif key == "group":
                    group = val
                break
        else:
            # Skip totals and standalone labels
            if is_total_line(raw):
                continue
            if looks_like_standalone_label(cells):
                continue

            # Data row: item, barcode, qty, amount
            if branch and group and len(cells) >= 4:
                item = first
                qty = parse_number(cells[2])
                amount = parse_number(cells[3])

                if item and qty is not None:
                    records.append({
                        "branch": branch,
                        "division": division or "",
                        "group": group,
                        "item": item,
                        "qty": qty,
                        "amount": amount if amount is not None else 0.0,
                    })

    df = pd.DataFrame(records)
    if not df.empty:
        # --- modifier flag ---
        df["is_modifier"] = (df["amount"] == 0) & (df["qty"] > 0)

        # --- richer category tagging ---
        df["category"] = "core_food"  # default for non-beverage paid items
        df.loc[df["is_modifier"], "category"] = "modifier"
        df.loc[df["division"].str.contains(_COFFEE_HOT_PATTERN, na=False), "category"] = "coffee_hot"
        df.loc[df["division"].str.contains(_COFFEE_COLD_PATTERN, na=False), "category"] = "coffee_cold"
        df.loc[df["division"].str.contains(_SHAKE_PATTERN, na=False), "category"] = "milkshake"
        # catch remaining beverages that aren't coffee/shake
        mask_bev = df["division"].str.contains(_BEVERAGE_PATTERN, na=False) & (
            df["category"].isin(["core_food", "modifier"])
        )
        df.loc[mask_bev, "category"] = "other_beverage"

        # --- share & ranking (non-modifier items only) ---
        paid = df[~df["is_modifier"]].copy()
        if not paid.empty:
            branch_total = paid.groupby("branch")["amount"].transform("sum")
            paid["item_sales_share_within_branch"] = (
                paid["amount"] / branch_total.replace(0, 1)
            ).round(6)
            paid["item_rank_within_branch"] = (
                paid.groupby("branch")["amount"]
                .rank(method="dense", ascending=False)
                .astype(int)
            )
            paid["item_rank_within_division"] = (
                paid.groupby(["branch", "division"])["amount"]
                .rank(method="dense", ascending=False)
                .astype(int)
            )
            df = df.merge(
                paid[["branch", "item", "item_sales_share_within_branch",
                      "item_rank_within_branch", "item_rank_within_division"]],
                on=["branch", "item"],
                how="left",
            )
        else:
            df["item_sales_share_within_branch"] = None
            df["item_rank_within_branch"] = None
            df["item_rank_within_division"] = None
    return df
