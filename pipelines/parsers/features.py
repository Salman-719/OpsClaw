"""
Feature store — builds reusable analytical feature tables from cleaned pipeline outputs.

Four feature tables:
  feat_branch_month      — demand trend, growth, volatility, channel/beverage share
  feat_branch_item       — item rank, share, attach tendency, beverage opportunity
  feat_customer_delivery  — RFM-style features (recency, frequency, value, segment)
  feat_branch_shift      — median labour hours, staff count, shift mix, intensity proxy
"""

import numpy as np
import pandas as pd


# ── feat_branch_month ─────────────────────────────────────────────────────────

def build_feat_branch_month(
    monthly_sales_df: pd.DataFrame,
    avg_sales_df: pd.DataFrame | None = None,
    items_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Branch-month demand features.
    Columns: branch, month, year, date, revenue,
             revenue_ma3 (3-month moving avg), mom_growth,
             volatility (std of growth), channel_delivery_share, beverage_share
    """
    if monthly_sales_df is None or monthly_sales_df.empty:
        return pd.DataFrame()

    df = monthly_sales_df.copy().sort_values(["branch", "date"])

    # Moving average and momentum
    df["revenue_ma3"] = df.groupby("branch")["revenue"].transform(
        lambda s: s.rolling(3, min_periods=1).mean()
    ).round(2)
    df["mom_growth"] = df.groupby("branch")["revenue"].transform(
        lambda s: s.pct_change()
    ).round(4)
    df["volatility"] = df.groupby("branch")["revenue"].transform(
        lambda s: s.pct_change().expanding().std()
    ).round(4)

    # Attach channel delivery share (static from avg_sales, spread to all months)
    if avg_sales_df is not None and not avg_sales_df.empty:
        branch_total = avg_sales_df.groupby("branch")["sales"].sum()
        delivery = avg_sales_df[avg_sales_df["channel"] == "DELIVERY"].set_index("branch")["sales"]
        del_share = (delivery / branch_total.replace(0, 1)).rename("channel_delivery_share").round(4)
        df = df.merge(del_share, left_on="branch", right_index=True, how="left")
    else:
        df["channel_delivery_share"] = None

    # Attach beverage share (static from items, spread to all months)
    if items_df is not None and not items_df.empty and "category" in items_df.columns:
        paid = items_df[~items_df.get("is_modifier", False)]
        branch_amt = paid.groupby("branch")["amount"].sum()
        bev_cats = ["coffee_hot", "coffee_cold", "milkshake", "other_beverage"]
        bev_amt = paid[paid["category"].isin(bev_cats)].groupby("branch")["amount"].sum()
        bev_share = (bev_amt / branch_amt.replace(0, 1)).rename("beverage_share").round(4)
        df = df.merge(bev_share, left_on="branch", right_index=True, how="left")
    else:
        df["beverage_share"] = None

    return df.reset_index(drop=True)


# ── feat_branch_item ──────────────────────────────────────────────────────────

def build_feat_branch_item(items_df: pd.DataFrame) -> pd.DataFrame:
    """
    Item-level features within branches.
    Columns: branch, item, division, group, category, qty, amount,
             item_share, item_rank, attach_tendency, beverage_opportunity_flag
    """
    if items_df is None or items_df.empty:
        return pd.DataFrame()

    paid = items_df[~items_df["is_modifier"]].copy()
    if paid.empty:
        return pd.DataFrame()

    branch_total = paid.groupby("branch")["amount"].transform("sum")
    paid["item_share"] = (paid["amount"] / branch_total.replace(0, 1)).round(6)
    paid["item_rank"] = (
        paid.groupby("branch")["amount"]
        .rank(method="dense", ascending=False)
        .astype(int)
    )

    # Attach tendency: qty / branch total qty — how often this item is added
    branch_qty = paid.groupby("branch")["qty"].transform("sum")
    paid["attach_tendency"] = (paid["qty"] / branch_qty.replace(0, 1)).round(6)

    # Beverage opportunity flag — non-beverage items that could pair with beverages
    bev_cats = {"coffee_hot", "coffee_cold", "milkshake", "other_beverage"}
    paid["beverage_opportunity_flag"] = ~paid["category"].isin(bev_cats)

    cols = [
        "branch", "item", "division", "group", "category", "qty", "amount",
        "item_share", "item_rank", "attach_tendency", "beverage_opportunity_flag",
    ]
    return paid[[c for c in cols if c in paid.columns]].reset_index(drop=True)


# ── feat_customer_delivery ────────────────────────────────────────────────────

def build_feat_customer_delivery(customer_df: pd.DataFrame) -> pd.DataFrame:
    """
    RFM-style customer features.
    Columns: phone, branch, customer, total, num_orders, recency_days,
             customer_lifespan_days, avg_order_value, is_repeat_customer,
             value_segment (high / medium / low)
    """
    if customer_df is None or customer_df.empty:
        return pd.DataFrame()

    df = customer_df.copy()

    # Exclude zero-value rows for segmentation
    active = df[~df["is_zero_value_customer"]].copy()
    if active.empty:
        df["value_segment"] = "low"
        return df

    # Value segmentation by percentile within branch (avoid groupby.apply)
    active["value_segment"] = "medium"  # default
    for branch_name, grp in active.groupby("branch"):
        q66 = grp["total"].quantile(0.66)
        q33 = grp["total"].quantile(0.33)
        idx = grp.index
        active.loc[idx[grp["total"] <= q33], "value_segment"] = "low"
        active.loc[idx[grp["total"] > q66], "value_segment"] = "high"

    df = df.merge(
        active[["branch", "customer", "value_segment"]],
        on=["branch", "customer"],
        how="left",
    )
    df["value_segment"] = df["value_segment"].fillna("low")

    return df.reset_index(drop=True)


# ── feat_branch_shift ─────────────────────────────────────────────────────────

def build_feat_branch_shift(attendance_df: pd.DataFrame) -> pd.DataFrame:
    """
    Branch-level staffing features (from valid shifts only).
    Columns: branch, median_hours, mean_hours, total_shifts, valid_shifts,
             unique_employees, morning_pct, afternoon_pct, evening_pct,
             weekend_shift_pct, anomaly_rate
    """
    if attendance_df is None or attendance_df.empty:
        return pd.DataFrame()

    df = attendance_df.copy()
    all_shifts = df.groupby("branch").agg(
        total_shifts=("emp_id", "count"),
        anomaly_rate=("is_anomalous", "mean"),
    ).round(4)

    valid = df[df.get("is_valid_shift", ~df["is_anomalous"])].copy()
    if valid.empty:
        return all_shifts.reset_index()

    feats = valid.groupby("branch").agg(
        median_hours=("duration_hours", "median"),
        mean_hours=("duration_hours", "mean"),
        valid_shifts=("emp_id", "count"),
        unique_employees=("emp_id", "nunique"),
    ).round(2)

    # Shift mix percentages
    shift_counts = valid.groupby(["branch", "shift_type"]).size().unstack(fill_value=0)
    total_valid = shift_counts.sum(axis=1)
    for st in ("morning", "afternoon", "evening"):
        if st in shift_counts.columns:
            feats[f"{st}_pct"] = (shift_counts[st] / total_valid).round(4)
        else:
            feats[f"{st}_pct"] = 0.0

    # Weekend shift percentage
    if "weekend_flag" in valid.columns:
        wk = valid.groupby("branch")["weekend_flag"].mean().rename("weekend_shift_pct").round(4)
        feats = feats.join(wk)

    result = feats.join(all_shifts).reset_index()
    return result
