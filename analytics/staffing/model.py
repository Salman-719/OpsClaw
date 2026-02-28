from __future__ import annotations

import math

import pandas as pd

from .config import (
    LOW_CONFIDENCE_MIN_TARGET_SLOTS,
    LOW_CONFIDENCE_TARGET_CAP_MULTIPLE,
    MIN_PRODUCTIVITY_TARGET,
    TARGET_FALLBACK_SHIFT,
)


def shift_bucket_from_hour(hour: int) -> str:
    if 6 <= hour <= 11:
        return "morning"
    if 12 <= hour <= 16:
        return "afternoon"
    if 17 <= hour <= 23:
        return "evening"
    return "overnight"


def _robust_target(values: pd.Series) -> float:
    values = values.dropna()
    values = values.loc[values > 0]
    if values.empty:
        return MIN_PRODUCTIVITY_TARGET

    q1 = values.quantile(0.25)
    q3 = values.quantile(0.75)
    iqr = q3 - q1
    lower = max(0.0, q1 - 1.5 * iqr)
    upper = q3 + 1.5 * iqr
    trimmed = values.loc[(values >= lower) & (values <= upper)]
    if trimmed.empty:
        trimmed = values
    return max(float(trimmed.median()), MIN_PRODUCTIVITY_TARGET)


def build_target_productivity_reference(
    supply_profile: pd.DataFrame,
    total_demand_est_hourly: pd.DataFrame,
) -> pd.DataFrame:
    joined = supply_profile.merge(
        total_demand_est_hourly[
            [
                "branch",
                "day_of_week",
                "hour",
                "total_orders_est_base",
                "confidence",
            ]
        ],
        on=["branch", "day_of_week", "hour"],
        how="left",
    )

    joined["total_orders_est_base"] = joined["total_orders_est_base"].fillna(0.0)
    joined["shift_bucket"] = joined["hour"].apply(shift_bucket_from_hour)
    joined["observed_orders_per_employee"] = 0.0

    staffed_mask = joined["avg_active_employees"] > 0
    joined.loc[staffed_mask, "observed_orders_per_employee"] = (
        joined.loc[staffed_mask, "total_orders_est_base"]
        / joined.loc[staffed_mask, "avg_active_employees"]
    )

    branch_shift = (
        joined.groupby(["branch", "shift_bucket"], as_index=False)
        .agg(
            slot_count=("observed_orders_per_employee", lambda s: int((s > 0).sum())),
            median_observed_orders_per_employee=("observed_orders_per_employee", "median"),
        )
    )
    branch_shift["target_orders_per_employee"] = (
        joined.groupby(["branch", "shift_bucket"])["observed_orders_per_employee"]
        .apply(_robust_target)
        .values
    )
    branch_shift.loc[
        branch_shift["slot_count"] == 0, "target_orders_per_employee"
    ] = pd.NA
    branch_shift["reference_level"] = "branch_shift"

    branch_all = (
        joined.groupby("branch", as_index=False)
        .agg(
            slot_count=("observed_orders_per_employee", lambda s: int((s > 0).sum())),
            median_observed_orders_per_employee=("observed_orders_per_employee", "median"),
        )
    )
    branch_all["shift_bucket"] = TARGET_FALLBACK_SHIFT
    branch_all["target_orders_per_employee"] = (
        joined.groupby("branch")["observed_orders_per_employee"].apply(_robust_target).values
    )
    branch_all.loc[
        branch_all["slot_count"] == 0, "target_orders_per_employee"
    ] = pd.NA
    branch_all["reference_level"] = "branch_all_day"

    global_target = _robust_target(joined["observed_orders_per_employee"])
    global_row = pd.DataFrame(
        [
            {
                "branch": "__global__",
                "shift_bucket": TARGET_FALLBACK_SHIFT,
                "slot_count": int((joined["observed_orders_per_employee"] > 0).sum()),
                "median_observed_orders_per_employee": joined[
                    "observed_orders_per_employee"
                ].median(),
                "target_orders_per_employee": global_target,
                "reference_level": "global",
            }
        ]
    )

    reference = pd.concat([branch_shift, branch_all, global_row], ignore_index=True)
    branch_confidence = (
        total_demand_est_hourly.groupby("branch", as_index=False)["confidence"].first()
    )
    reference = reference.merge(branch_confidence, on="branch", how="left")

    low_conf_sparse_mask = (
        reference["confidence"].eq("low")
        & reference["reference_level"].isin(["branch_shift", "branch_all_day"])
        & (reference["slot_count"] < LOW_CONFIDENCE_MIN_TARGET_SLOTS)
    )
    reference.loc[low_conf_sparse_mask, "target_orders_per_employee"] = pd.NA

    low_conf_cap_mask = (
        reference["confidence"].eq("low")
        & reference["reference_level"].isin(["branch_shift", "branch_all_day"])
        & reference["target_orders_per_employee"].notna()
    )
    reference.loc[low_conf_cap_mask, "target_orders_per_employee"] = reference.loc[
        low_conf_cap_mask, "target_orders_per_employee"
    ].clip(upper=global_target * LOW_CONFIDENCE_TARGET_CAP_MULTIPLE)

    reference["target_orders_per_employee"] = reference[
        "target_orders_per_employee"
    ].astype(float).round(4)
    reference["median_observed_orders_per_employee"] = reference[
        "median_observed_orders_per_employee"
    ].fillna(0.0).round(4)

    return reference.sort_values(["branch", "shift_bucket"]).reset_index(drop=True)


def estimate_required_staff(
    supply_profile: pd.DataFrame,
    total_demand_est_hourly: pd.DataFrame,
    target_productivity_reference: pd.DataFrame,
) -> pd.DataFrame:
    combined = supply_profile.merge(
        total_demand_est_hourly,
        on=["branch", "day_of_week", "hour"],
        how="left",
    )

    for col in [
        "avg_active_employees",
        "median_active_employees",
        "min_active_employees",
        "max_active_employees",
        "slot_observations",
        "observed_days",
        "support_rows",
        "slot_num_orders",
        "branch_total_customer_rows_in_overlap",
        "branch_total_num_orders_in_overlap",
        "shape_weight_rows",
        "shape_weight_num_orders",
        "delivery_orders_est",
        "total_orders_est_low",
        "total_orders_est_base",
        "total_orders_est_high",
    ]:
        if col in combined:
            combined[col] = combined[col].fillna(0.0)

    combined["shift_bucket"] = combined["hour"].apply(shift_bucket_from_hour)

    shift_targets = target_productivity_reference.loc[
        target_productivity_reference["reference_level"] == "branch_shift",
        ["branch", "shift_bucket", "target_orders_per_employee"],
    ].rename(columns={"target_orders_per_employee": "shift_target"})

    branch_targets = target_productivity_reference.loc[
        target_productivity_reference["reference_level"] == "branch_all_day",
        ["branch", "target_orders_per_employee"],
    ].rename(columns={"target_orders_per_employee": "branch_target"})

    global_target = float(
        target_productivity_reference.loc[
            (target_productivity_reference["branch"] == "__global__")
            & (target_productivity_reference["shift_bucket"] == TARGET_FALLBACK_SHIFT),
            "target_orders_per_employee",
        ].iloc[0]
    )

    combined = combined.merge(shift_targets, on=["branch", "shift_bucket"], how="left")
    combined = combined.merge(branch_targets, on="branch", how="left")
    combined["target_orders_per_employee"] = (
        combined["shift_target"]
        .fillna(combined["branch_target"])
        .fillna(global_target)
        .round(4)
    )

    def _required_staff(value: float, target: float) -> int:
        if value <= 0 or target <= 0:
            return 0
        return int(math.ceil(value / target))

    combined["required_employees_low"] = combined.apply(
        lambda row: _required_staff(row["total_orders_est_low"], row["target_orders_per_employee"]),
        axis=1,
    )
    combined["required_employees_base"] = combined.apply(
        lambda row: _required_staff(row["total_orders_est_base"], row["target_orders_per_employee"]),
        axis=1,
    )
    combined["required_employees_high"] = combined.apply(
        lambda row: _required_staff(row["total_orders_est_high"], row["target_orders_per_employee"]),
        axis=1,
    )

    # Staffed operating slots should never recommend fewer than one employee.
    combined["required_employees_low"] = combined["required_employees_low"].clip(lower=1)
    combined["required_employees_base"] = combined["required_employees_base"].clip(lower=1)
    combined["required_employees_high"] = combined["required_employees_high"].clip(lower=1)

    combined["gap_low"] = (
        combined["required_employees_low"] - combined["avg_active_employees"]
    ).round(2)
    combined["gap_base"] = (
        combined["required_employees_base"] - combined["avg_active_employees"]
    ).round(2)
    combined["gap_high"] = (
        combined["required_employees_high"] - combined["avg_active_employees"]
    ).round(2)

    combined["status"] = "balanced"
    combined.loc[combined["gap_base"] >= 1.0, "status"] = "understaffed"
    combined.loc[combined["gap_base"] <= -1.0, "status"] = "overstaffed"

    return combined.sort_values(["branch", "day_of_week", "hour"]).reset_index(drop=True)


def summarize_staffing_findings(
    staffing_gap_hourly: pd.DataFrame,
    branch_demand_multipliers: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict] = []

    for branch, group in staffing_gap_hourly.groupby("branch"):
        under = group.loc[group["status"] == "understaffed"].sort_values(
            "gap_base", ascending=False
        )
        over = group.loc[group["status"] == "overstaffed"].sort_values("gap_base")

        worst_under = under.iloc[0] if not under.empty else None
        worst_over = over.iloc[0] if not over.empty else None
        multiplier_row = branch_demand_multipliers.loc[
            branch_demand_multipliers["branch"] == branch
        ].iloc[0]

        top_under_slots = "; ".join(
            f"{row.day_of_week} {int(row.hour):02d}:00 (gap {row.gap_base:.2f})"
            for row in under.head(3).itertuples()
        )
        top_over_slots = "; ".join(
            f"{row.day_of_week} {int(row.hour):02d}:00 (gap {row.gap_base:.2f})"
            for row in over.head(3).itertuples()
        )

        if not under.empty:
            recommendation = (
                "Increase staffing around the highest-gap slots before widening other shifts."
            )
        elif not over.empty:
            recommendation = "Trim low-demand slots or reassign employees to busier periods."
        else:
            recommendation = "Current staffing looks balanced under the base-demand scenario."

        rows.append(
            {
                "branch": branch,
                "demand_confidence": multiplier_row["confidence"],
                "share_source": multiplier_row["share_source"],
                "analysis_slots": int(len(group)),
                "understaffed_slots": int((group["status"] == "understaffed").sum()),
                "balanced_slots": int((group["status"] == "balanced").sum()),
                "overstaffed_slots": int((group["status"] == "overstaffed").sum()),
                "avg_active_employees_across_slots": round(
                    float(group["avg_active_employees"].mean()), 2
                ),
                "avg_required_employees_base": round(
                    float(group["required_employees_base"].mean()), 2
                ),
                "worst_understaffed_slot": (
                    f"{worst_under.day_of_week} {int(worst_under.hour):02d}:00"
                    if worst_under is not None
                    else ""
                ),
                "worst_understaffed_gap": (
                    round(float(worst_under.gap_base), 2) if worst_under is not None else 0.0
                ),
                "worst_overstaffed_slot": (
                    f"{worst_over.day_of_week} {int(worst_over.hour):02d}:00"
                    if worst_over is not None
                    else ""
                ),
                "worst_overstaffed_gap": (
                    round(float(worst_over.gap_base), 2) if worst_over is not None else 0.0
                ),
                "top_understaffed_slots": top_under_slots,
                "top_overstaffed_slots": top_over_slots,
                "recommendation": recommendation,
            }
        )

    return pd.DataFrame(rows).sort_values("branch").reset_index(drop=True)
