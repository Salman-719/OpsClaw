from __future__ import annotations

from datetime import timedelta

import pandas as pd

from .config import DAY_ORDER


def _shift_datetimes(row: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_ts = pd.to_datetime(f"{row['date'].date()} {row['punch_in']}")
    end_ts = pd.to_datetime(f"{row['date'].date()} {row['punch_out']}")
    if end_ts < start_ts:
        end_ts += timedelta(days=1)
    return start_ts, end_ts


def build_attendance_hourly_supply(attendance: pd.DataFrame) -> pd.DataFrame:
    valid = attendance.loc[attendance["is_valid_shift"]].copy()
    if valid.empty:
        return pd.DataFrame(
            columns=[
                "branch",
                "date",
                "day_of_week",
                "hour",
                "active_employees",
                "active_shift_rows",
            ]
        )

    rows: list[dict] = []
    for record in valid.itertuples(index=False):
        start_ts, end_ts = _shift_datetimes(pd.Series(record._asdict()))
        current_hour = start_ts.floor("h")
        while current_hour < end_ts:
            hour_end = current_hour + pd.Timedelta(hours=1)
            if start_ts < hour_end and end_ts > current_hour:
                rows.append(
                    {
                        "branch": record.branch,
                        "date": current_hour.normalize(),
                        "day_of_week": current_hour.day_name(),
                        "hour": current_hour.hour,
                        "emp_id": record.emp_id,
                        "shift_date": record.date,
                    }
                )
            current_hour = hour_end

    hourly_employee_slots = pd.DataFrame(rows)
    if hourly_employee_slots.empty:
        return pd.DataFrame(
            columns=[
                "branch",
                "date",
                "day_of_week",
                "hour",
                "active_employees",
                "active_shift_rows",
            ]
        )

    hourly = (
        hourly_employee_slots.drop_duplicates(
            subset=["branch", "date", "hour", "emp_id", "shift_date"]
        )
        .groupby(["branch", "date", "day_of_week", "hour"], as_index=False)
        .agg(
            active_employees=("emp_id", "nunique"),
            active_shift_rows=("shift_date", "size"),
        )
    )

    hourly["day_of_week"] = pd.Categorical(
        hourly["day_of_week"], categories=DAY_ORDER, ordered=True
    )
    return hourly.sort_values(["branch", "date", "hour"]).reset_index(drop=True)


def build_supply_profile(staffing_supply_hourly: pd.DataFrame) -> pd.DataFrame:
    if staffing_supply_hourly.empty:
        return pd.DataFrame(
            columns=[
                "branch",
                "day_of_week",
                "hour",
                "avg_active_employees",
                "median_active_employees",
                "min_active_employees",
                "max_active_employees",
                "slot_observations",
                "observed_days",
            ]
        )

    profile = (
        staffing_supply_hourly.groupby(["branch", "day_of_week", "hour"], as_index=False)
        .agg(
            avg_active_employees=("active_employees", "mean"),
            median_active_employees=("active_employees", "median"),
            min_active_employees=("active_employees", "min"),
            max_active_employees=("active_employees", "max"),
            slot_observations=("active_employees", "size"),
            observed_days=("date", "nunique"),
        )
    )

    profile["avg_active_employees"] = profile["avg_active_employees"].round(2)
    return profile.sort_values(["branch", "day_of_week", "hour"]).reset_index(drop=True)
