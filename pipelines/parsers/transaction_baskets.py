"""
Pipeline 5: Transaction Baskets (Delivery Detail)

Uses report-block boundaries (Person_XXXX → Total) as pseudo-baskets.
Each block = one basket. Same person appearing in different branches = separate baskets.

Outputs three tables:
  raw_lines:       branch, customer, basket_id, item, qty, price
  audit_lines:     branch, customer, basket_id, item, qty, price, is_void, is_modifier
  basket_core:     basket_id, branch, customer, items_list, unique_items, net_qty, net_total
                   (core paid items only — excludes modifiers and voids — for Apriori/FP-Growth)
"""

import re
import pandas as pd
from .utils import (
    read_lines, parse_csv_line, parse_number,
    is_noise, is_date_line, is_total_line,
)

SIGNATURE = "sales by customer in details"

_BRANCH_RE = re.compile(r"^Branch\s*:\s*(.+)", re.IGNORECASE)
_PERSON_RE = re.compile(r"^Person_\d+")
_COL_HEADER_RE = re.compile(r"Full Name\s*,\s*Qty", re.IGNORECASE)


def can_parse(lines: list[str]) -> bool:
    return SIGNATURE in " ".join(lines[:5]).lower()


def parse(filepath: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lines = read_lines(filepath)
    raw_rows = []
    branch = customer = None
    basket_id = 0

    for line in lines:
        raw = line.strip()
        if is_noise(raw) or is_date_line(raw):
            continue
        if _COL_HEADER_RE.match(raw):
            continue
        if "sales by customer" in raw.lower():
            continue

        cells = parse_csv_line(raw)
        if not cells:
            continue

        first = cells[0]

        # Branch header
        m = _BRANCH_RE.match(first)
        if m:
            branch = m.group(1).strip().rstrip(",")
            continue

        # Skip totals (block-level "Total :" and "Total Branch:")
        if is_total_line(raw):
            continue

        # Customer header → new basket
        if _PERSON_RE.match(first):
            customer = first
            basket_id += 1
            continue

        # Data row: empty first cell, qty, item, price
        if branch and customer and not first and len(cells) >= 4:
            qty = parse_number(cells[1])
            item = cells[2].strip()
            price = parse_number(cells[3])

            if item and qty is not None:
                raw_rows.append({
                    "branch": branch,
                    "customer": customer,
                    "basket_id": basket_id,
                    "item": item,
                    "qty": qty,
                    "price": price if price is not None else 0.0,
                })

    # ── Table A: raw_lines ──
    raw_df = pd.DataFrame(raw_rows)
    if raw_df.empty:
        empty_audit = pd.DataFrame(columns=[
            "branch", "customer", "basket_id", "item", "qty", "price", "is_void", "is_modifier",
        ])
        empty_basket = pd.DataFrame(columns=[
            "basket_id", "branch", "customer", "items_list", "unique_items", "net_qty", "net_total",
        ])
        return raw_df, empty_audit, empty_basket

    # ── Table B: audit_lines (with flags) ──
    audit_df = raw_df.copy()
    audit_df["is_void"] = audit_df["qty"] < 0
    audit_df["is_modifier"] = (audit_df["price"] == 0.0) & (~audit_df["is_void"])

    # ── Table C: basket_core (paid items only, for Apriori / FP-Growth) ──
    core = audit_df[(~audit_df["is_void"]) & (~audit_df["is_modifier"])].copy()

    if core.empty:
        basket_df = pd.DataFrame(columns=[
            "basket_id", "branch", "customer", "items_list", "unique_items", "net_qty", "net_total",
        ])
    else:
        basket_df = (
            core.groupby(["basket_id", "branch", "customer"])
            .agg(
                items_list=("item", list),
                unique_items=("item", "nunique"),
                net_qty=("qty", "sum"),
                net_total=("price", "sum"),
            )
            .reset_index()
        )
        basket_df = basket_df[basket_df["net_qty"] > 0].reset_index(drop=True)

    return raw_df, audit_df, basket_df
