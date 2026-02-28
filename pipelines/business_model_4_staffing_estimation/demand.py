from __future__ import annotations

import pandas as pd

from pipelines.business_model_4_staffing_estimation.config import (
    HIGH_CONFIDENCE_SHARE_SPREAD,
    LOW_CONFIDENCE_SHARE_SPREAD,
    LOW_CONFIDENCE_SALES_UPLIFT_CAP,
    MAX_DELIVERY_SHARE,
    MAX_SPARSE_SHAPE_TO_UNIFORM_RATIO,
    MEDIUM_CONFIDENCE_SHARE_SPREAD,
    MIN_SHAPE_SUPPORT_ROWS,
    MIN_DELIVERY_SHARE,
)


def _clamp_share(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return max(MIN_DELIVERY_SHARE, min(MAX_DELIVERY_SHARE, float(value)))


def build_delivery_demand_shape(
    customer_orders: pd.DataFrame,
    staffed_slots: pd.DataFrame,
    overlap_start: pd.Timestamp,
    overlap_end: pd.Timestamp,
) -> pd.DataFrame:
    base_slots = staffed_slots[["branch", "day_of_week", "hour"]].drop_duplicates().copy()
    branches = sorted(base_slots["branch"].unique().tolist())
    overlap_finish = overlap_end + pd.Timedelta(days=1)
    window = customer_orders.loc[
        customer_orders["branch"].isin(branches)
        & (customer_orders["last_order"] >= overlap_start)
        & (customer_orders["last_order"] < overlap_finish)
    ].copy()

    if window.empty:
        base = base_slots.copy()
        branch_staffed_slot_count = (
            base.groupby("branch", as_index=False).size().rename(columns={"size": "branch_staffed_slot_count"})
        )
        base = base.merge(branch_staffed_slot_count, on="branch", how="left")
        base["support_rows"] = 0
        base["slot_num_orders"] = 0.0
        base["branch_total_customer_rows_in_overlap"] = 0
        base["branch_total_num_orders_in_overlap"] = 0.0
        base["shape_weight_rows"] = 0.0
        base["shape_weight_num_orders"] = 0.0
        base["shape_support_strength"] = 0.0
        return base

    window["day_of_week"] = window["last_order"].dt.day_name()
    window["hour"] = window["last_order"].dt.hour

    slot_counts = (
        window.groupby(["branch", "day_of_week", "hour"], as_index=False)
        .agg(
            support_rows=("customer", "size"),
            slot_num_orders=("num_orders", "sum"),
        )
    )

    branch_totals = (
        window.groupby("branch", as_index=False)
        .agg(
            branch_total_customer_rows_in_overlap=("customer", "size"),
            branch_total_num_orders_in_overlap=("num_orders", "sum"),
        )
    )

    branch_staffed_slot_count = (
        base_slots.groupby("branch", as_index=False).size().rename(columns={"size": "branch_staffed_slot_count"})
    )

    shape = base_slots.merge(
        slot_counts, on=["branch", "day_of_week", "hour"], how="left"
    )
    shape = shape.merge(branch_totals, on="branch", how="left")
    shape = shape.merge(branch_staffed_slot_count, on="branch", how="left")

    shape["support_rows"] = shape["support_rows"].fillna(0).astype(int)
    shape["slot_num_orders"] = shape["slot_num_orders"].fillna(0.0)
    shape["branch_total_customer_rows_in_overlap"] = (
        shape["branch_total_customer_rows_in_overlap"].fillna(0).astype(int)
    )
    shape["branch_total_num_orders_in_overlap"] = (
        shape["branch_total_num_orders_in_overlap"].fillna(0.0)
    )

    shape["shape_weight_rows"] = 0.0
    rows_mask = shape["branch_total_customer_rows_in_overlap"] > 0
    shape.loc[rows_mask, "shape_weight_rows"] = (
        shape.loc[rows_mask, "support_rows"]
        / shape.loc[rows_mask, "branch_total_customer_rows_in_overlap"]
    )
    shape["shape_support_strength"] = 0.0
    shape.loc[rows_mask, "shape_support_strength"] = (
        shape.loc[rows_mask, "branch_total_customer_rows_in_overlap"] / MIN_SHAPE_SUPPORT_ROWS
    ).clip(upper=1.0)
    uniform_weight = 1.0 / shape["branch_staffed_slot_count"]
    shape.loc[rows_mask, "shape_weight_rows"] = (
        shape.loc[rows_mask, "shape_support_strength"] * shape.loc[rows_mask, "shape_weight_rows"]
        + (1.0 - shape.loc[rows_mask, "shape_support_strength"]) * uniform_weight.loc[rows_mask]
    )
    sparse_mask = rows_mask & (shape["shape_support_strength"] < 1.0)
    shape.loc[sparse_mask, "shape_weight_rows"] = shape.loc[sparse_mask, "shape_weight_rows"].clip(
        upper=(uniform_weight.loc[sparse_mask] * MAX_SPARSE_SHAPE_TO_UNIFORM_RATIO)
    )
    branch_weight_sums = shape.groupby("branch")["shape_weight_rows"].transform("sum")
    renorm_mask = branch_weight_sums > 0
    shape.loc[renorm_mask, "shape_weight_rows"] = (
        shape.loc[renorm_mask, "shape_weight_rows"] / branch_weight_sums.loc[renorm_mask]
    )

    shape["shape_weight_num_orders"] = 0.0
    orders_mask = shape["branch_total_num_orders_in_overlap"] > 0
    shape.loc[orders_mask, "shape_weight_num_orders"] = (
        shape.loc[orders_mask, "slot_num_orders"]
        / shape.loc[orders_mask, "branch_total_num_orders_in_overlap"]
    )

    return shape.sort_values(["branch", "day_of_week", "hour"]).reset_index(drop=True)


def build_branch_demand_multipliers(
    avg_sales_menu: pd.DataFrame,
    customer_orders: pd.DataFrame,
    monthly_sales: pd.DataFrame,
    branches: list[str],
    overlap_start: pd.Timestamp,
    overlap_end: pd.Timestamp,
) -> pd.DataFrame:
    total_customers = (
        avg_sales_menu.groupby("branch", as_index=False)["customers"]
        .sum()
        .rename(columns={"customers": "avg_sales_total_customers"})
    )
    delivery_rows = avg_sales_menu.loc[avg_sales_menu["channel"] == "DELIVERY", [
        "branch",
        "customers",
        "customer_share_within_branch",
    ]].rename(
        columns={
            "customers": "avg_sales_delivery_customers",
            "customer_share_within_branch": "avg_sales_delivery_share",
        }
    )
    customer_profiles = (
        customer_orders.groupby("branch", as_index=False)
        .agg(
            delivery_customer_profiles=("customer", "size"),
            delivery_num_orders=("num_orders", "sum"),
        )
    )

    overlap_finish = overlap_end + pd.Timedelta(days=1)
    overlap_orders = customer_orders.loc[
        (customer_orders["last_order"] >= overlap_start)
        & (customer_orders["last_order"] < overlap_finish)
    ].groupby("branch", as_index=False)["num_orders"].sum().rename(
        columns={"num_orders": "overlap_num_orders"}
    )

    recent_month = (
        monthly_sales.sort_values(["branch", "date"])
        .groupby("branch", as_index=False)
        .tail(1)[["branch", "date", "revenue"]]
        .rename(columns={"date": "recent_revenue_month", "revenue": "recent_revenue"})
    )

    diagnostics = (
        pd.DataFrame({"branch": branches})
        .merge(total_customers, on="branch", how="left")
        .merge(delivery_rows, on="branch", how="left")
        .merge(customer_profiles, on="branch", how="left")
        .merge(overlap_orders, on="branch", how="left")
        .merge(recent_month, on="branch", how="left")
    )

    diagnostics["avg_sales_total_customers"] = diagnostics["avg_sales_total_customers"].fillna(0.0)
    diagnostics["avg_sales_delivery_customers"] = diagnostics["avg_sales_delivery_customers"].fillna(0.0)
    diagnostics["avg_sales_delivery_share"] = diagnostics["avg_sales_delivery_share"].fillna(0.0)
    diagnostics["delivery_customer_profiles"] = diagnostics["delivery_customer_profiles"].fillna(0).astype(int)
    diagnostics["delivery_num_orders"] = diagnostics["delivery_num_orders"].fillna(0.0)
    diagnostics["overlap_num_orders"] = diagnostics["overlap_num_orders"].fillna(0.0)
    diagnostics["recent_revenue"] = diagnostics["recent_revenue"].fillna(0.0)

    observed_share = pd.Series([None] * len(diagnostics), dtype="float64")
    mask = diagnostics["avg_sales_total_customers"] > 0
    observed_share.loc[mask] = (
        diagnostics.loc[mask, "delivery_customer_profiles"]
        / diagnostics.loc[mask, "avg_sales_total_customers"]
    )
    diagnostics["observed_profile_share"] = observed_share.apply(_clamp_share)

    known_shares = diagnostics.loc[
        diagnostics["avg_sales_delivery_share"] > 0, "avg_sales_delivery_share"
    ]
    global_base_share = _clamp_share(
        float(known_shares.median()) if not known_shares.empty else MIN_DELIVERY_SHARE
    )

    total_recent_revenue = float(diagnostics["recent_revenue"].sum())
    total_overlap_orders = float(diagnostics["overlap_num_orders"].sum())

    rows: list[dict] = []
    for record in diagnostics.itertuples(index=False):
        note = ""
        if record.avg_sales_delivery_share > 0:
            share_base = _clamp_share(record.avg_sales_delivery_share)
            spread = HIGH_CONFIDENCE_SHARE_SPREAD
            share_source = "avg_sales_menu_delivery_share"
            confidence = "high"
            if record.observed_profile_share is not None and record.observed_profile_share > 0:
                ratio_gap = abs(record.observed_profile_share - share_base) / share_base
                if ratio_gap > 1.0:
                    confidence = "medium"
                    spread = MEDIUM_CONFIDENCE_SHARE_SPREAD
                    note = "avg_sales_menu and customer_orders profile counts disagree"
        elif record.observed_profile_share is not None and record.observed_profile_share > 0:
            share_base = _clamp_share(record.observed_profile_share)
            spread = LOW_CONFIDENCE_SHARE_SPREAD
            share_source = "customer_orders_profile_share"
            confidence = "low"
            note = "delivery share inferred because avg_sales_menu has no delivery row"
        else:
            share_base = global_base_share
            spread = LOW_CONFIDENCE_SHARE_SPREAD
            share_source = "global_delivery_share_fallback"
            confidence = "low"
            note = "delivery share inferred from global fallback"

        share_low = _clamp_share(share_base * (1 - spread))
        share_high = _clamp_share(share_base * (1 + spread))

        revenue_share = (
            float(record.recent_revenue) / total_recent_revenue if total_recent_revenue > 0 else 0.0
        )
        proxy_share = (
            float(record.overlap_num_orders) / total_overlap_orders if total_overlap_orders > 0 else 0.0
        )
        coverage_gap_ratio = revenue_share / proxy_share if proxy_share > 0 else 1.0
        sales_uplift = 1.0
        if confidence == "low" and revenue_share > 0 and proxy_share > 0:
            sales_uplift = min(
                LOW_CONFIDENCE_SALES_UPLIFT_CAP,
                max(1.0, coverage_gap_ratio ** 0.5),
            )
            if sales_uplift > 1.0:
                note = (note + "; " if note else "") + "sales uplift applied for underrepresented proxy demand"
        elif confidence == "low" and revenue_share > 0 and proxy_share == 0:
            sales_uplift = LOW_CONFIDENCE_SALES_UPLIFT_CAP
            note = (note + "; " if note else "") + "max sales uplift applied because proxy demand is missing"

        rows.append(
            {
                "branch": record.branch,
                "avg_sales_total_customers": record.avg_sales_total_customers,
                "avg_sales_delivery_customers": record.avg_sales_delivery_customers,
                "avg_sales_delivery_share": record.avg_sales_delivery_share,
                "delivery_customer_profiles": record.delivery_customer_profiles,
                "delivery_num_orders": record.delivery_num_orders,
                "observed_profile_share": record.observed_profile_share,
                "share_source": share_source,
                "confidence": confidence,
                "note": note,
                "recent_revenue_month": record.recent_revenue_month,
                "recent_revenue": record.recent_revenue,
                "recent_revenue_share_staffed_branches": round(revenue_share, 6),
                "overlap_proxy_order_share": round(proxy_share, 6),
                "sales_to_proxy_gap_ratio": round(coverage_gap_ratio, 4),
                "sales_calibration_multiplier": round(sales_uplift, 4),
                "delivery_share_low": round(share_low, 6),
                "delivery_share_base": round(share_base, 6),
                "delivery_share_high": round(share_high, 6),
                "multiplier_low_demand": round((1 / share_high) * sales_uplift, 4),
                "multiplier_base_demand": round((1 / share_base) * sales_uplift, 4),
                "multiplier_high_demand": round((1 / share_low) * sales_uplift, 4),
            }
        )

    return pd.DataFrame(rows).sort_values("branch").reset_index(drop=True)


def estimate_total_hourly_demand(
    delivery_demand_shape_hourly: pd.DataFrame,
    branch_demand_multipliers: pd.DataFrame,
) -> pd.DataFrame:
    demand = delivery_demand_shape_hourly.merge(
        branch_demand_multipliers,
        on="branch",
        how="left",
        validate="many_to_one",
    )

    demand["delivery_orders_est"] = (
        demand["branch_total_num_orders_in_overlap"] * demand["shape_weight_rows"]
    )
    demand["total_orders_est_low"] = (
        demand["delivery_orders_est"] * demand["multiplier_low_demand"]
    )
    demand["total_orders_est_base"] = (
        demand["delivery_orders_est"] * demand["multiplier_base_demand"]
    )
    demand["total_orders_est_high"] = (
        demand["delivery_orders_est"] * demand["multiplier_high_demand"]
    )

    for col in [
        "delivery_orders_est",
        "total_orders_est_low",
        "total_orders_est_base",
        "total_orders_est_high",
    ]:
        demand[col] = demand[col].round(4)

    return demand.sort_values(["branch", "day_of_week", "hour"]).reset_index(drop=True)
