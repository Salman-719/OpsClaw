"""
kpis.py
=======
Feature 3 – Expansion Feasibility  |  KPI Computation Layer

Computes the following KPIs per canonical branch, sourced from cleaned DataFrames:

PRIMARY (from monthly_sales):
  avg_monthly_revenue   – mean of monthly totals
  recent_growth_rate    – OLS slope / first-to-last pct-change over observed months
  revenue_volatility    – std / mean  (coefficient of variation, lower = more stable)

SECONDARY – best-effort (graceful degradation if source unavailable):
  avg_order_value       – from customer_orders_delivery; per-order spend
  orders_count          – total delivery orders per branch
  delivery_share        – fraction of revenue from delivery channel; from delivery_detail
  staff_efficiency      – revenue per total employee-hour; from attendance + revenue
  tax_burden            – total_tax / avg_monthly_revenue (annualised); from tax_summary

All KPIs are expressed as raw (un-normalised) values.
Normalisation is handled in scoring.py.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from .utils import get_logger, CANONICAL_BRANCHES

logger = get_logger("feature_3.kpis")

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _ols_slope(values: list[float]) -> float:
    """Return the OLS slope of values vs index (normalised so index spans [0,1])."""
    n = len(values)
    if n < 2:
        return 0.0
    x = np.linspace(0, 1, n)
    y = np.array(values, dtype=float)
    # slope = cov(x,y) / var(x)
    vx = np.var(x)
    if vx == 0:
        return 0.0
    return float(np.cov(x, y)[0, 1] / vx)


def _pct_change_first_last(values: list[float]) -> float:
    """Percentage change from first to last value. Returns 0.0 if undefined."""
    if len(values) < 2 or values[0] == 0:
        return 0.0
    return (values[-1] - values[0]) / abs(values[0])


# ──────────────────────────────────────────────────────────────────────────────
# PRIMARY KPIs  (monthly_sales)
# ──────────────────────────────────────────────────────────────────────────────

def compute_revenue_kpis(monthly_sales: pd.DataFrame) -> pd.DataFrame:
    """
    Compute avg_monthly_revenue, recent_growth_rate, revenue_volatility per branch.

    `recent_growth_rate` is a blend:
      - OLS slope across all observed months (normalised to % of mean revenue):
        captures trend direction robustly.
      - Also stored as pct_change_first_last for transparency.

    The combined `recent_growth_rate` is the OLS slope divided by the branch mean
    revenue, yielding a dimensionless growth-intensity metric.

    Parameters
    ----------
    monthly_sales : output of cleaning.parse_monthly_sales

    Returns
    -------
    DataFrame indexed by branch with columns:
        avg_monthly_revenue, recent_growth_rate, revenue_volatility,
        pct_change_first_last, n_months, is_partial_history
    """
    if monthly_sales.empty:
        logger.warning("revenue_kpis: empty input")
        return pd.DataFrame(columns=[
            "branch", "avg_monthly_revenue", "recent_growth_rate",
            "revenue_volatility", "pct_change_first_last", "n_months", "is_partial_history",
        ])

    records = []
    for branch, grp in monthly_sales.groupby("branch"):
        # Sort chronologically
        grp = grp.sort_values(["year", "month_num"])
        rev_series = grp["revenue"].tolist()
        mean_rev   = np.mean(rev_series)
        std_rev    = np.std(rev_series, ddof=1) if len(rev_series) > 1 else 0.0

        slope           = _ols_slope(rev_series)
        growth_rate     = slope / mean_rev if mean_rev != 0 else 0.0   # dimensionless
        pct_fl          = _pct_change_first_last(rev_series)
        volatility      = std_rev / mean_rev if mean_rev != 0 else 0.0
        n_months        = len(rev_series)
        is_partial      = n_months < 12   # flag if < 1 full year observed

        records.append({
            "branch":                branch,
            "avg_monthly_revenue":   mean_rev,
            "recent_growth_rate":    growth_rate,
            "revenue_volatility":    volatility,
            "pct_change_first_last": pct_fl,
            "n_months":              n_months,
            "is_partial_history":    is_partial,
        })

    df = pd.DataFrame(records).set_index("branch")
    logger.info("revenue_kpis: computed for branches: %s", df.index.tolist())
    return df


# ──────────────────────────────────────────────────────────────────────────────
# SECONDARY KPI — orders & avg order value  (customer_orders)
# ──────────────────────────────────────────────────────────────────────────────

def compute_order_kpis(customer_orders: pd.DataFrame) -> pd.DataFrame:
    """
    Compute orders_count and avg_order_value per branch from delivery orders.

    Returns DataFrame indexed by branch with columns:
        orders_count, avg_order_value, total_customer_revenue
    """
    if customer_orders.empty:
        logger.warning("order_kpis: empty input")
        return pd.DataFrame(columns=["branch", "orders_count", "avg_order_value", "total_customer_revenue"])

    agg = (
        customer_orders
        .groupby("branch")
        .agg(
            orders_count           = ("num_orders",      "sum"),
            total_customer_revenue = ("total",           "sum"),
        )
        .reset_index()
    )
    agg["avg_order_value"] = agg["total_customer_revenue"] / agg["orders_count"].replace(0, np.nan)
    agg = agg.set_index("branch")
    logger.info("order_kpis: computed for branches: %s", agg.index.tolist())
    return agg


# ──────────────────────────────────────────────────────────────────────────────
# SECONDARY KPI — delivery share  (delivery_detail)
# ──────────────────────────────────────────────────────────────────────────────

def compute_delivery_kpis(delivery_detail: pd.DataFrame) -> pd.DataFrame:
    """
    Compute delivery_revenue and delivery_order_count per branch.

    The delivery_detail file is entirely from the delivery channel, so:
      delivery_revenue = sum of price*qty per branch

    Returns DataFrame indexed by branch with columns:
        delivery_revenue, delivery_order_count
    """
    if delivery_detail.empty:
        logger.warning("delivery_kpis: empty input")
        return pd.DataFrame(columns=["branch", "delivery_revenue", "delivery_order_count"])

    agg = (
        delivery_detail
        .assign(line_revenue=lambda x: x["qty"] * x["price"])
        .groupby("branch")
        .agg(
            delivery_revenue      = ("line_revenue",  "sum"),
            delivery_order_count  = ("customer",      "nunique"),
        )
        .reset_index()
        .set_index("branch")
    )
    logger.info("delivery_kpis: computed for branches: %s", agg.index.tolist())
    return agg


# ──────────────────────────────────────────────────────────────────────────────
# SECONDARY KPI — staff efficiency  (attendance + revenue)
# ──────────────────────────────────────────────────────────────────────────────

def compute_staff_efficiency(
    attendance: pd.DataFrame,
    revenue_kpis: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute staff_efficiency = annualised revenue / total employee-hours.

    Uses attendance hours × (12 / n_months) to scale to annual if < 12 months
    of data are present (best-effort).

    Returns DataFrame indexed by branch with columns:
        total_hours, revenue_per_hour
    """
    if attendance.empty:
        logger.warning("staff_efficiency: empty attendance input")
        return pd.DataFrame(columns=["branch", "total_hours", "revenue_per_hour"])

    hours = (
        attendance
        .groupby("branch")["duration_hours"]
        .sum()
        .rename("total_hours")
        .reset_index()
        .set_index("branch")
    )

    merged = hours.join(revenue_kpis[["avg_monthly_revenue", "n_months"]], how="left")
    merged["annualised_revenue"] = (
        merged["avg_monthly_revenue"] * merged["n_months"].fillna(5)
    )
    merged["revenue_per_hour"] = merged["annualised_revenue"] / merged["total_hours"].replace(0, np.nan)
    logger.info("staff_efficiency: computed for branches: %s", merged.index.tolist())
    return merged[["total_hours", "revenue_per_hour"]]


# ──────────────────────────────────────────────────────────────────────────────
# SECONDARY KPI — tax burden  (tax_summary)
# ──────────────────────────────────────────────────────────────────────────────

def compute_tax_kpis(
    tax_summary: pd.DataFrame,
    revenue_kpis: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute tax_burden = total_tax / (avg_monthly_revenue * n_months).

    Returns DataFrame indexed by branch with columns:
        total_tax, tax_burden
    """
    if tax_summary.empty:
        logger.warning("tax_kpis: empty input")
        return pd.DataFrame(columns=["branch", "total_tax", "tax_burden"])

    tax = (
        tax_summary
        .groupby("branch")["total_tax"]
        .sum()
        .reset_index()
        .set_index("branch")
    )
    merged = tax.join(revenue_kpis[["avg_monthly_revenue", "n_months"]], how="left")
    merged["period_revenue"] = merged["avg_monthly_revenue"] * merged["n_months"].fillna(5)
    merged["tax_burden"] = merged["total_tax"] / merged["period_revenue"].replace(0, np.nan)
    logger.info("tax_kpis: computed for branches: %s", merged.index.tolist())
    return merged[["total_tax", "tax_burden"]]


# ──────────────────────────────────────────────────────────────────────────────
# COMBINED: build branch_kpis table
# ──────────────────────────────────────────────────────────────────────────────

def build_branch_kpis(sources: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Assemble all KPIs into a single branch-indexed DataFrame.

    `sources` is the dict returned by cleaning.load_all_sources().

    Missing secondary sources are handled gracefully:
      - Absent columns are filled with NaN; scoring.py will impute them.

    Returns
    -------
    DataFrame with index = branch and columns:
        avg_monthly_revenue, recent_growth_rate, revenue_volatility,
        pct_change_first_last, n_months, is_partial_history,
        orders_count, avg_order_value, total_customer_revenue,
        delivery_revenue, delivery_order_count, delivery_share,
        total_hours, revenue_per_hour,
        total_tax, tax_burden
    """
    monthly = sources.get("monthly_sales", pd.DataFrame())

    # Primary (required)
    rev = compute_revenue_kpis(monthly)
    if rev.empty:
        raise ValueError(
            "monthly_sales is empty or could not be parsed. "
            "Cannot compute feasibility without revenue data."
        )

    # Secondary (best-effort)
    ord_kpis  = compute_order_kpis(sources.get("customer_orders", pd.DataFrame()))
    deliv     = compute_delivery_kpis(sources.get("delivery_detail", pd.DataFrame()))
    staff     = compute_staff_efficiency(sources.get("attendance", pd.DataFrame()), rev)
    tax       = compute_tax_kpis(sources.get("tax_summary", pd.DataFrame()), rev)

    kpis = rev.copy()

    for frame in [ord_kpis, deliv, staff, tax]:
        if not frame.empty:
            kpis = kpis.join(frame, how="left")

    # Delivery share: delivery_revenue / (avg_monthly_revenue * n_months)
    if "delivery_revenue" in kpis.columns and "avg_monthly_revenue" in kpis.columns:
        period_rev = kpis["avg_monthly_revenue"] * kpis["n_months"].fillna(5)
        kpis["delivery_share"] = (
            kpis["delivery_revenue"] / period_rev.replace(0, np.nan)
        ).clip(0, 1)

    # Ensure all expected columns exist (fill missing with NaN)
    _expected = [
        "avg_monthly_revenue", "recent_growth_rate", "revenue_volatility",
        "pct_change_first_last", "n_months", "is_partial_history",
        "orders_count", "avg_order_value", "total_customer_revenue",
        "delivery_revenue", "delivery_order_count", "delivery_share",
        "total_hours", "revenue_per_hour",
        "total_tax", "tax_burden",
    ]
    for col in _expected:
        if col not in kpis.columns:
            kpis[col] = np.nan

    kpis = kpis[_expected].copy()
    kpis.index.name = "branch"
    kpis = kpis.reset_index()

    logger.info(
        "build_branch_kpis: final table shape %s, branches: %s",
        kpis.shape, kpis["branch"].tolist(),
    )
    return kpis
