#!/usr/bin/env python3
"""Standalone Business Model 4 staffing estimator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from .config import (
    DEFAULT_OUTPUT_DIR,
    PIPELINES_OUTPUT_DIR,
)
from .demand import (
    build_branch_demand_multipliers,
    build_delivery_demand_shape,
    estimate_total_hourly_demand,
)
from .loaders import (
    infer_overlap_window,
    load_input_tables,
)
from .model import (
    build_target_productivity_reference,
    estimate_required_staff,
    summarize_staffing_findings,
)
from .supply import (
    build_attendance_hourly_supply,
    build_supply_profile,
)


def _save(df: pd.DataFrame, output_dir: Path, filename: str, verbose: bool) -> None:
    path = output_dir / filename
    df.to_csv(path, index=False)
    if verbose:
        print(f"  saved {filename} ({len(df)} rows x {len(df.columns)} cols)")


def run(
    input_dir: Path | str = PIPELINES_OUTPUT_DIR,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    verbose: bool = True,
) -> dict[str, pd.DataFrame]:
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    tables = load_input_tables(input_path)
    attendance = tables["attendance"]
    branches = sorted(
        attendance.loc[attendance["is_valid_shift"], "branch"].dropna().unique().tolist()
    )
    overlap_start, overlap_end = infer_overlap_window(attendance)

    if verbose:
        print(f"Input dir:  {input_path}")
        print(f"Output dir: {output_path}")
        print(f"Branches:   {', '.join(branches)}")
        print(f"Window:     {overlap_start.date()} to {overlap_end.date()}")

    staffing_supply_hourly = build_attendance_hourly_supply(attendance)
    supply_profile = build_supply_profile(staffing_supply_hourly)
    delivery_demand_shape_hourly = build_delivery_demand_shape(
        tables["customer_orders"],
        staffed_slots=supply_profile,
        overlap_start=overlap_start,
        overlap_end=overlap_end,
    )
    branch_demand_multipliers = build_branch_demand_multipliers(
        tables["avg_sales_menu"],
        tables["customer_orders"],
        tables["monthly_sales"],
        branches=branches,
        overlap_start=overlap_start,
        overlap_end=overlap_end,
    )
    total_demand_est_hourly = estimate_total_hourly_demand(
        delivery_demand_shape_hourly,
        branch_demand_multipliers,
    )
    target_productivity_reference = build_target_productivity_reference(
        supply_profile,
        total_demand_est_hourly,
    )
    staffing_gap_hourly = estimate_required_staff(
        supply_profile,
        total_demand_est_hourly,
        target_productivity_reference,
    )
    branch_staffing_findings = summarize_staffing_findings(
        staffing_gap_hourly,
        branch_demand_multipliers,
    )

    outputs = {
        "staffing_supply_hourly.csv": staffing_supply_hourly,
        "delivery_demand_shape_hourly.csv": delivery_demand_shape_hourly,
        "branch_demand_multipliers.csv": branch_demand_multipliers,
        "target_productivity_reference.csv": target_productivity_reference,
        "total_demand_est_hourly.csv": total_demand_est_hourly,
        "staffing_gap_hourly.csv": staffing_gap_hourly,
        "branch_staffing_findings.csv": branch_staffing_findings,
    }

    for filename, dataframe in outputs.items():
        _save(dataframe, output_path, filename, verbose)

    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Business Model 4 staffing estimator")
    parser.add_argument(
        "--input-dir",
        default=str(PIPELINES_OUTPUT_DIR),
        help="Path to the cleaned pipeline output directory",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where staffing estimation outputs will be saved",
    )
    args = parser.parse_args()
    run(args.input_dir, args.output_dir)
