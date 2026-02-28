from __future__ import annotations

from pathlib import Path

import pandas as pd

from pipelines.business_model_4_staffing_estimation.config import PIPELINES_OUTPUT_DIR


def _normalize_bool(series: pd.Series) -> pd.Series:
    mapped = series.astype(str).str.strip().str.lower().map(
        {"true": True, "false": False, "1": True, "0": False}
    )
    return mapped.fillna(False)


def load_input_tables(input_dir: Path | str = PIPELINES_OUTPUT_DIR) -> dict[str, pd.DataFrame]:
    input_path = Path(input_dir)

    attendance = pd.read_csv(input_path / "attendance.csv")
    attendance["date"] = pd.to_datetime(attendance["date"])
    attendance["duration_hours"] = pd.to_numeric(attendance["duration_hours"], errors="coerce")
    attendance["shift_start_hour"] = pd.to_numeric(attendance["shift_start_hour"], errors="coerce")
    attendance["is_anomalous"] = _normalize_bool(attendance["is_anomalous"])
    attendance["is_valid_shift"] = _normalize_bool(attendance["is_valid_shift"])
    attendance["weekend_flag"] = _normalize_bool(attendance["weekend_flag"])

    customer_orders = pd.read_csv(input_path / "customer_orders.csv")
    customer_orders["first_order"] = pd.to_datetime(customer_orders["first_order"])
    customer_orders["last_order"] = pd.to_datetime(customer_orders["last_order"])
    customer_orders["total"] = pd.to_numeric(customer_orders["total"], errors="coerce")
    customer_orders["num_orders"] = pd.to_numeric(
        customer_orders["num_orders"], errors="coerce"
    ).fillna(0)
    customer_orders["is_zero_value_customer"] = _normalize_bool(
        customer_orders["is_zero_value_customer"]
    )
    customer_orders["is_repeat_customer"] = _normalize_bool(
        customer_orders["is_repeat_customer"]
    )

    avg_sales_menu = pd.read_csv(input_path / "avg_sales_menu.csv")
    for col in [
        "customers",
        "sales",
        "avg_per_customer",
        "sales_share_within_branch",
        "customer_share_within_branch",
    ]:
        avg_sales_menu[col] = pd.to_numeric(avg_sales_menu[col], errors="coerce")

    dim_branch = pd.read_csv(input_path / "dim_branch.csv")
    for col in [
        "has_delivery",
        "has_table",
        "has_takeaway",
        "has_monthly_sales",
        "has_attendance_data",
    ]:
        dim_branch[col] = _normalize_bool(dim_branch[col])

    monthly_sales = pd.read_csv(input_path / "monthly_sales.csv")
    monthly_sales["date"] = pd.to_datetime(monthly_sales["date"])
    monthly_sales["revenue"] = pd.to_numeric(monthly_sales["revenue"], errors="coerce")

    return {
        "attendance": attendance,
        "customer_orders": customer_orders,
        "avg_sales_menu": avg_sales_menu,
        "dim_branch": dim_branch,
        "monthly_sales": monthly_sales,
    }


def infer_overlap_window(attendance: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    valid = attendance.loc[attendance["is_valid_shift"]].copy()
    if valid.empty:
        raise ValueError("attendance.csv has no valid shifts to anchor the analysis window")
    return valid["date"].min().normalize(), valid["date"].max().normalize()
