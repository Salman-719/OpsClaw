"""
kpis.py – Branch-level beverage KPI computation.

Computes:
  - total_orders_per_branch
  - beverage_orders_per_branch   (baskets containing any target beverage)
  - beverage_attachment_rate     = beverage_orders / total_orders
  - beverage_gap_to_best         = best_rate - branch_rate
  - bev_revenue_share            = beverage amount / total amount (from feat_branch_item)
"""
from __future__ import annotations

from typing import List

import pandas as pd

from .beverage_detection import is_target_beverage
from .parsing import parse_items_list
from .utils import get_logger

_log = get_logger(__name__)


def compute_basket_kpis(basket_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute attachment-rate KPIs from the basket core table.

    Parameters
    ----------
    basket_df : pd.DataFrame
        As returned by loader.load_basket_core(); must have
        columns ``branch`` and ``items_list``.

    Returns
    -------
    pd.DataFrame
        One row per branch with columns:
        branch, total_orders, beverage_orders, beverage_attachment_rate,
        best_branch_rate, beverage_gap_to_best.
    """
    _log.info("Computing basket-level beverage KPIs …")

    # Parse items lists once and store as Python lists
    basket_df = basket_df.copy()
    basket_df["_items"] = basket_df["items_list"].apply(parse_items_list)

    # Flag baskets that contain at least one target beverage
    basket_df["_has_bev"] = basket_df["_items"].apply(
        lambda items: any(is_target_beverage(i) for i in items)
    )

    grouped = (
        basket_df.groupby("branch")
        .agg(
            total_orders=("basket_id", "count"),
            beverage_orders=("_has_bev", "sum"),
        )
        .reset_index()
    )

    grouped["beverage_attachment_rate"] = (
        grouped["beverage_orders"] / grouped["total_orders"]
    ).round(4)

    best_rate = grouped["beverage_attachment_rate"].max()
    grouped["best_branch_rate"] = round(best_rate, 4)
    grouped["beverage_gap_to_best"] = (
        best_rate - grouped["beverage_attachment_rate"]
    ).round(4)

    _log.info(
        "Basket KPIs done. Best branch rate=%.3f", best_rate
    )
    return grouped.sort_values("beverage_attachment_rate", ascending=False)


def compute_revenue_kpis(branch_item_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute beverage revenue share per branch from feat_branch_item.

    Parameters
    ----------
    branch_item_df : pd.DataFrame
        As returned by loader.load_branch_item().

    Returns
    -------
    pd.DataFrame
        One row per branch with columns:
        branch, total_amount, bev_amount, bev_revenue_share.
    """
    _log.info("Computing revenue-based beverage KPIs …")
    df = branch_item_df.copy()

    # Mark beverage rows using the category column (faster than string matching)
    bev_categories = {"coffee_hot", "coffee_cold", "milkshake", "other_beverage"}
    df["_is_bev"] = df["category"].isin(bev_categories)

    rev = (
        df.groupby("branch")
        .apply(
            lambda g: pd.Series(
                {
                    "total_amount": g["amount"].sum(),
                    "bev_amount": g.loc[g["_is_bev"], "amount"].sum(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    rev["bev_revenue_share"] = (rev["bev_amount"] / rev["total_amount"]).round(4)
    return rev


def merge_kpis(
    basket_kpis: pd.DataFrame, revenue_kpis: pd.DataFrame
) -> pd.DataFrame:
    """
    Left-join basket and revenue KPIs on ``branch``.

    Basket KPIs are the left (primary) table so only branches that appear
    in the transaction data are kept.  Branches present only in
    feat_branch_item (no basket records) are excluded — they cannot have
    a meaningful attachment rate.

    Returns a combined DataFrame with all KPI columns.
    """
    merged = pd.merge(basket_kpis, revenue_kpis, on="branch", how="left")
    return merged
