#!/usr/bin/env python3
"""Generate staffing summary CSV tables."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from .config import DEFAULT_OUTPUT_DIR


def _load_tables(output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    staffing_gap = pd.read_csv(output_dir / "staffing_gap_hourly.csv")
    findings = pd.read_csv(output_dir / "branch_staffing_findings.csv")

    for col in [
        "hour",
        "avg_active_employees",
        "required_employees_base",
        "delivery_orders_est",
        "total_orders_est_base",
        "gap_base",
    ]:
        staffing_gap[col] = pd.to_numeric(staffing_gap[col], errors="coerce")

    return staffing_gap, findings


def build_branch_summary_tables(
    staffing_gap: pd.DataFrame, findings: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    branch_hourly = (
        staffing_gap.groupby("branch", as_index=False)
        .agg(
            staffed_slots=("hour", "size"),
            avg_active_employees=("avg_active_employees", "mean"),
            avg_required_employees=("required_employees_base", "mean"),
            avg_gap=("gap_base", "mean"),
            peak_required_employees=("required_employees_base", "max"),
            peak_gap=("gap_base", "max"),
        )
    )
    branch_hourly["avg_active_employees"] = branch_hourly["avg_active_employees"].round(2)
    branch_hourly["avg_required_employees"] = branch_hourly["avg_required_employees"].round(2)
    branch_hourly["avg_gap"] = branch_hourly["avg_gap"].round(2)
    branch_hourly["peak_gap"] = branch_hourly["peak_gap"].round(2)

    summary = branch_hourly.merge(
        findings[
            [
                "branch",
                "demand_confidence",
                "understaffed_slots",
                "balanced_slots",
                "overstaffed_slots",
                "worst_understaffed_slot",
                "worst_overstaffed_slot",
                "recommendation",
            ]
        ],
        on="branch",
        how="left",
    )

    top_slots = staffing_gap.copy()
    top_slots["abs_gap"] = top_slots["gap_base"].abs()
    top_slots = top_slots.sort_values(["branch", "abs_gap"], ascending=[True, False])
    top_slots = (
        top_slots.groupby("branch", as_index=False)
        .head(10)[
            [
                "branch",
                "day_of_week",
                "hour",
                "avg_active_employees",
                "required_employees_base",
                "delivery_orders_est",
                "total_orders_est_base",
                "gap_base",
                "status",
            ]
        ]
        .reset_index(drop=True)
    )

    return summary, top_slots


def run(output_dir: Path | str = DEFAULT_OUTPUT_DIR, verbose: bool = True) -> dict[str, Path]:
    output_path = Path(output_dir)

    staffing_gap, findings = _load_tables(output_path)
    summary, top_slots = build_branch_summary_tables(staffing_gap, findings)

    summary_csv = output_path / "branch_summary_view.csv"
    top_slots_csv = output_path / "top_gap_slots.csv"
    summary.to_csv(summary_csv, index=False)
    top_slots.to_csv(top_slots_csv, index=False)

    outputs = {
        "branch_summary_view.csv": summary_csv,
        "top_gap_slots.csv": top_slots_csv,
    }

    if verbose:
        print(f"Visual output dir: {output_path}")
        for label, path in outputs.items():
            print(f"  saved {label}: {path}")

    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate staffing summary CSV tables")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory containing staffing analysis CSV outputs",
    )
    args = parser.parse_args()
    run(args.output_dir)
