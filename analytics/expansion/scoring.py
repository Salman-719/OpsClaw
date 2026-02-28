"""
scoring.py
==========
Feature 3 – Expansion Feasibility  |  Normalisation & Scoring Layer

Transforms raw KPIs into a composite feasibility score per branch.

WEIGHT RATIONALE (documented for agent/summary output):
  growth    : 0.30  – Sales trend is the strongest signal for expansion;
                       a growing branch demonstrates unmet demand.
  revenue   : 0.25  – Absolute revenue reflects market size.
  stability : 0.15  – Low volatility reduces execution risk.
  avg_order : 0.15  – Higher per-order value means better unit economics.
  delivery  : 0.10  – Strong delivery channel signals untapped geographic reach.
  ops_eff   : 0.05  – Revenue per staff-hour: operational maturity.
                       Weighted least because attendance data covers 1 month.

  Note: tax_burden is used as a mild *penalty* (higher tax = slight down-weight)
        but is not a primary component; it adjusts ops_efficiency indirectly
        and is reported separately in the KPI table.

FORMULA:
  stability    = 1 – norm(revenue_volatility)
  feasibility  = 0.30*norm(growth) + 0.25*norm(revenue)
               + 0.15*stability
               + 0.15*norm(avg_order_value)
               + 0.10*norm(delivery_share)
               + 0.05*norm(revenue_per_hour)

Missing values are imputed with the column median; if all values are missing,
the component receives the neutral value 0.5.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from .utils import get_logger

logger = get_logger("feature_3.scoring")

# ──────────────────────────────────────────────────────────────────────────────
# WEIGHTS  (must sum to 1.0)
# ──────────────────────────────────────────────────────────────────────────────

WEIGHTS: dict[str, float] = {
    "growth":      0.30,
    "revenue":     0.25,
    "stability":   0.15,
    "avg_order":   0.15,
    "delivery":    0.10,
    "ops_eff":     0.05,
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"

# ──────────────────────────────────────────────────────────────────────────────
# NORMALISATION
# ──────────────────────────────────────────────────────────────────────────────

def _minmax(series: pd.Series) -> pd.Series:
    """
    Min-max normalise a series to [0, 1].
    If all values are identical or all NaN, returns 0.5 (neutral imputation).
    """
    s = series.copy().astype(float)
    s_valid = s.dropna()
    if s_valid.empty or s_valid.max() == s_valid.min():
        return pd.Series(0.5, index=s.index)
    result = (s - s_valid.min()) / (s_valid.max() - s_valid.min())
    return result.fillna(0.5)   # impute remaining NaN with neutral


def _impute_median(series: pd.Series) -> pd.Series:
    """Fill NaN with the column median; if all NaN use 0.5."""
    s = series.copy().astype(float)
    median = s.median()
    if np.isnan(median):
        return s.fillna(0.5)
    return s.fillna(median)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN SCORING FUNCTION
# ──────────────────────────────────────────────────────────────────────────────

def compute_feasibility_scores(branch_kpis: pd.DataFrame) -> pd.DataFrame:
    """
    Given the raw KPI table from kpis.build_branch_kpis(), produce a scored
    table with normalised components and the composite feasibility score.

    Parameters
    ----------
    branch_kpis : DataFrame with column 'branch' plus raw KPI columns.

    Returns
    -------
    DataFrame with columns:
        branch,
        # raw KPIs (carried through)
        avg_monthly_revenue, recent_growth_rate, revenue_volatility,
        avg_order_value, delivery_share, revenue_per_hour,
        # normalised components
        norm_growth, norm_revenue, norm_volatility, norm_avg_order,
        norm_delivery, norm_ops_eff,
        # derived
        stability,
        # composite
        feasibility_score,
        # metadata
        score_tier (High / Medium / Low)
    """
    df = branch_kpis.copy().set_index("branch")

    # ── Impute secondary KPIs before normalising ────────────────────────────
    for col in ["avg_order_value", "delivery_share", "revenue_per_hour"]:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = _impute_median(df[col])

    # ── Normalise each component ────────────────────────────────────────────
    df["norm_growth"]    = _minmax(df["recent_growth_rate"])
    df["norm_revenue"]   = _minmax(df["avg_monthly_revenue"])
    df["norm_volatility"]= _minmax(df["revenue_volatility"])   # higher vol → higher norm
    df["norm_avg_order"] = _minmax(df["avg_order_value"])
    df["norm_delivery"]  = _minmax(df["delivery_share"])
    df["norm_ops_eff"]   = _minmax(df["revenue_per_hour"])

    # ── Stability = 1 - normalised_volatility ───────────────────────────────
    df["stability"] = 1.0 - df["norm_volatility"]

    # ── Composite score ──────────────────────────────────────────────────────
    df["feasibility_score"] = (
        WEIGHTS["growth"]    * df["norm_growth"]    +
        WEIGHTS["revenue"]   * df["norm_revenue"]   +
        WEIGHTS["stability"] * df["stability"]      +
        WEIGHTS["avg_order"] * df["norm_avg_order"] +
        WEIGHTS["delivery"]  * df["norm_delivery"]  +
        WEIGHTS["ops_eff"]   * df["norm_ops_eff"]
    ).round(4)

    # ── Tier ────────────────────────────────────────────────────────────────
    def _tier(score: float) -> str:
        if score >= 0.65:
            return "High"
        if score >= 0.45:
            return "Medium"
        return "Low"

    df["score_tier"] = df["feasibility_score"].apply(_tier)

    # ── Which component drove the score? (top 2 weighted contributions) ─────
    component_cols = {
        "growth":    ("norm_growth",    WEIGHTS["growth"]),
        "revenue":   ("norm_revenue",   WEIGHTS["revenue"]),
        "stability": ("stability",      WEIGHTS["stability"]),
        "avg_order": ("norm_avg_order", WEIGHTS["avg_order"]),
        "delivery":  ("norm_delivery",  WEIGHTS["delivery"]),
        "ops_eff":   ("norm_ops_eff",   WEIGHTS["ops_eff"]),
    }

    def _top_drivers(row: pd.Series) -> str:
        contribs = {
            k: row[col] * w
            for k, (col, w) in component_cols.items()
        }
        ranked = sorted(contribs.items(), key=lambda x: x[1], reverse=True)
        return ", ".join(k for k, _ in ranked[:2])

    df["top_drivers"] = df.apply(_top_drivers, axis=1)

    df = df.reset_index()

    # Select output columns
    out_cols = [
        "branch",
        "avg_monthly_revenue", "recent_growth_rate", "revenue_volatility",
        "avg_order_value", "delivery_share", "revenue_per_hour",
        "norm_growth", "norm_revenue", "norm_volatility",
        "norm_avg_order", "norm_delivery", "norm_ops_eff",
        "stability",
        "feasibility_score", "score_tier", "top_drivers",
    ]
    # Only include columns that exist
    out_cols = [c for c in out_cols if c in df.columns]
    df = df[out_cols].sort_values("feasibility_score", ascending=False).reset_index(drop=True)

    logger.info(
        "feasibility_scores computed:\n%s",
        df[["branch", "feasibility_score", "score_tier"]].to_string(index=False),
    )
    return df


# ──────────────────────────────────────────────────────────────────────────────
# WEIGHT DOCUMENTATION  (used in summary.md and agent explanations)
# ──────────────────────────────────────────────────────────────────────────────

WEIGHT_RATIONALE: dict[str, str] = {
    "growth (0.30)": (
        "Sales trend is the strongest expansion signal. "
        "A branch with consistently increasing revenue demonstrates unmet local demand, "
        "validating that replicating this profile in the same region is likely to succeed."
    ),
    "revenue (0.25)": (
        "Absolute average monthly revenue reflects proven market size. "
        "High-revenue branches confirm that the local market can support operations."
    ),
    "stability (0.15)": (
        "Low revenue volatility (1 – normalised CV) indicates predictable cash flows, "
        "reducing execution risk for a new branch."
    ),
    "avg_order_value (0.15)": (
        "Higher spend per delivery order implies better unit economics and "
        "greater revenue potential per customer interaction."
    ),
    "delivery_share (0.10)": (
        "A strong delivery channel signals geographic demand beyond walk-in capacity, "
        "suggesting untapped market reach that a nearby branch could serve."
    ),
    "ops_efficiency (0.05)": (
        "Revenue per staff-hour is a proxy for operational maturity. "
        "Weighted lightly because attendance logs cover only one month of data."
    ),
}
