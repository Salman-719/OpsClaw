"""
Demand Forecast — Phase 4: Orchestrator
========================================
Runs prepare → ensemble → save.
Produces:
  output/demand_forecast_all.csv
  output/demand_forecast_by_branch/*.csv
  output/forecast_metadata.json
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import asdict
from datetime import datetime, timezone

import pandas as pd

_THIS_DIR = pathlib.Path(__file__).resolve().parent

from .prepare import prepare_all, BranchSeries
from .ensemble import ensemble_forecast, ForecastRow

# ── output paths ─────────────────────────────────────────────────────────
OUTPUT_DIR = _THIS_DIR / "output"
BY_BRANCH_DIR = OUTPUT_DIR / "demand_forecast_by_branch"


def _rel(path: pathlib.Path) -> pathlib.Path:
    """Safely display *path* relative to _THIS_DIR; fall back to name."""
    try:
        return path.relative_to(_THIS_DIR)
    except ValueError:
        return path

# ── branch-name → safe filename ─────────────────────────────────────────
_SAFE_NAMES = {
    "Conut": "conut",
    "Conut - Tyre": "conut_tyre",
    "Conut Jnah": "conut_jnah",
    "Main Street Coffee": "main_street_coffee",
}

# ── similarity reference mapping (plan §6) ───────────────────────────────
# MSC is data-starved (n_clean=3) → use Conut Jnah as reference
_SIMILARITY_REFS: dict[str, str] = {
    "Main Street Coffee": "Conut Jnah",
}

# ── column order for output CSV ──────────────────────────────────────────
_COLUMNS = [
    "branch",
    "scenario",
    "forecast_period",
    "is_primary",
    "forecast_month",
    "demand_index_forecast",
    "expected_change_vs_last_clean_month",
    "relative_band_low",
    "relative_band_high",
    "band_width_pct",
    "naive_estimate",
    "wma3_estimate",
    "linear_estimate",
    "similarity_estimate",
    "method",
    "confidence_level",
    "forecast_stability_score",
    "forecast_stability_label",
    "stability_data_qty",
    "stability_volatility",
    "stability_agreement",
    "stability_anomaly",
    "n_months_used",
    "last_clean_month",
    "december_anomaly_flag",
    "notes",
    "explanation",
]


def _rows_to_df(rows: list[ForecastRow]) -> pd.DataFrame:
    """Convert list of ForecastRow dataclasses → DataFrame."""
    records = [asdict(r) for r in rows]
    df = pd.DataFrame(records)
    # enforce column order
    for c in _COLUMNS:
        if c not in df.columns:
            df[c] = None
    return df[_COLUMNS]


def run() -> pd.DataFrame:
    """Main entry point.  Returns the combined DataFrame."""

    # ── Phase 1: prepare ─────────────────────────────────────────────────
    print("Phase 1  ▸  Loading & preparing data …")
    data = prepare_all()

    for name, bs in data.items():
        print(f"  {name:25s}  n_clean={bs.n_clean}  anomalies={bs.anomaly_flags}")

    # ── Phase 2+3: ensemble per branch ───────────────────────────────────
    print("\nPhase 2+3  ▸  Running estimators & ensemble …")
    all_rows: list[ForecastRow] = []

    for branch_name, bs in data.items():
        ref_name = _SIMILARITY_REFS.get(branch_name)
        ref_bs: BranchSeries | None = data.get(ref_name) if ref_name else None

        rows = ensemble_forecast(bs, reference_bs=ref_bs)
        all_rows.extend(rows)
        print(f"  {branch_name:25s}  → {len(rows)} rows")

    # ── Phase 4: save outputs ────────────────────────────────────────────
    print("\nPhase 4  ▸  Saving outputs …")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    BY_BRANCH_DIR.mkdir(parents=True, exist_ok=True)

    df = _rows_to_df(all_rows)

    # combined CSV
    all_path = OUTPUT_DIR / "demand_forecast_all.csv"
    df.to_csv(all_path, index=False)
    print(f"  ✓ {_rel(all_path)}")

    # per-branch CSVs
    for branch_name in df["branch"].unique():
        safe = _SAFE_NAMES.get(branch_name, branch_name.lower().replace(" ", "_"))
        branch_path = BY_BRANCH_DIR / f"{safe}.csv"
        df[df["branch"] == branch_name].to_csv(branch_path, index=False)
        print(f"  ✓ {_rel(branch_path)}")

    # metadata JSON
    meta = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_rows": len(df),
        "branches": sorted(df["branch"].unique().tolist()),
        "scenarios": sorted(df["scenario"].unique().tolist()),
        "periods_per_scenario": int(df["forecast_period"].max()),
        "parameters": {
            "PRIMARY_PERIODS": 1,
            "EXTENSION_PERIODS": 2,
            "WMA_WEIGHTS": [0.5, 0.3, 0.2],
            "ANOMALY_MOM_THRESHOLD_UP": 1.5,
            "ANOMALY_MOM_THRESHOLD_DOWN": -0.80,
            "CAPPED_VOLATILITY_MAX": 0.75,
            "DEC_SURGE_WEIGHT": 0.5,
            "DEC_PARTIAL_WEIGHT": 0.0,
            "TYRE_OCT_SPIKE_WEIGHT": 0.5,
            "SIMILARITY_ACTIVATION_THRESHOLD": 4,
            "SIMILARITY_WEIGHT_FACTOR": 0.5,
        },
        "anomaly_flags": {
            name: bs.anomaly_flags for name, bs in data.items()
        },
    }
    meta_path = OUTPUT_DIR / "forecast_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, default=str))
    print(f"  ✓ {_rel(meta_path)}")

    print(f"\nDone — {len(df)} total forecast rows.")
    return df


# ── CLI entry ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    df = run()
    print("\n" + "=" * 80)
    print("PRIMARY FORECASTS (period=1, both scenarios):\n")
    primary = df[df["is_primary"] == True].copy()  # noqa: E712
    cols = [
        "branch", "scenario", "forecast_month",
        "demand_index_forecast", "relative_band_low", "relative_band_high",
        "band_width_pct", "forecast_stability_score", "forecast_stability_label",
        "confidence_level",
    ]
    print(primary[cols].to_string(index=False))
