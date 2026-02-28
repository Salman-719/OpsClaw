"""
scoring.py – Growth potential scoring for branches.

Potential score combines three signals (each 0-1 normalised):
  1. low_attachment_score   = 1 - beverage_attachment_rate   (lower rate → higher score)
  2. order_volume_score     = total_orders / max(total_orders) (large base → higher score)
  3. assoc_lift_score       = avg top-5 lift for branch / max lift across branches

Final score = weighted average (weights configurable).

Higher score → higher growth opportunity.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from .utils import get_logger

_log = get_logger(__name__)

DEFAULT_WEIGHTS: Dict[str, float] = {
    "low_attachment": 0.35,
    "order_volume": 0.35,
    "assoc_lift": 0.30,
}


def _normalize_series(s: pd.Series) -> pd.Series:
    """Min-max normalise a Series to [0, 1]; handle constant series."""
    mn, mx = s.min(), s.max()
    if mx == mn:
        return pd.Series([0.5] * len(s), index=s.index)
    return (s - mn) / (mx - mn)


def compute_avg_lift(
    rules_df: pd.DataFrame, branch: str, top_n: int = 5
) -> float:
    """Return mean lift of top *top_n* rules for *branch*; 0 if none."""
    if rules_df.empty or "branch" not in rules_df.columns:
        return 0.0
    sub = rules_df[rules_df["branch"] == branch]
    if sub.empty:
        return 0.0
    return float(sub.nlargest(top_n, "lift")["lift"].mean())


def compute_growth_potential(
    kpis_df: pd.DataFrame,
    rules_df: pd.DataFrame,
    weights: Dict[str, float] = None,
) -> pd.DataFrame:
    """
    Score each branch by beverage growth potential.

    Parameters
    ----------
    kpis_df : pd.DataFrame
        Output of kpis.merge_kpis(); must contain columns:
        branch, beverage_attachment_rate, total_orders.
    rules_df : pd.DataFrame
        Output of basket_analysis.compute_rules_by_branch();
        must contain branch and lift columns.
    weights : dict, optional
        Override DEFAULT_WEIGHTS.

    Returns
    -------
    pd.DataFrame
        kpis_df augmented with:
        low_attachment_score, order_volume_score, assoc_lift_score,
        potential_score (0-1), potential_rank, top_rule_antecedent.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    _log.info("Computing growth potential scores (weights=%s) …", w)

    df = kpis_df.copy()

    # --- Signal 1: Low attachment (inverted rank) ---
    # Branches with NaN attachment (no basket data) get worst-case 0 attachment
    df["beverage_attachment_rate"] = df["beverage_attachment_rate"].fillna(0)
    df["beverage_gap_to_best"] = df["beverage_gap_to_best"].fillna(
        df["beverage_attachment_rate"].max()
    )
    df["low_attachment_score"] = _normalize_series(
        1 - df["beverage_attachment_rate"]
    )

    # --- Signal 2: Order volume ---
    df["order_volume_score"] = _normalize_series(df["total_orders"].fillna(0))

    # --- Signal 3: Association lift ---
    df["avg_lift"] = df["branch"].apply(lambda b: compute_avg_lift(rules_df, b))
    df["assoc_lift_score"] = _normalize_series(df["avg_lift"])

    # --- Weighted score ---
    df["potential_score"] = (
        w["low_attachment"] * df["low_attachment_score"]
        + w["order_volume"] * df["order_volume_score"]
        + w["assoc_lift"] * df["assoc_lift_score"]
    ).round(4)

    df["potential_rank"] = df["potential_score"].rank(ascending=False, method="min").astype(int)

    # --- Attach top rule antecedent for human-readable reason ---
    def _top_rule(branch: str) -> str:
        if rules_df.empty or "branch" not in rules_df.columns:
            return ""
        sub = rules_df[rules_df["branch"] == branch]
        if sub.empty:
            return ""
        top = sub.nlargest(1, "lift").iloc[0]
        return f"{top['antecedents']} → {top['consequents']} (lift={top['lift']:.2f})"

    df["top_bundle_rule"] = df["branch"].apply(_top_rule)

    return df.sort_values("potential_score", ascending=False).reset_index(drop=True)
