"""
Demand Forecast — Phase 1: Data Preparation
============================================
Loads monthly_sales, feat_branch_month, and dim_branch.
Flags anomalies, produces clean + december-weighted series per branch.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ── paths ────────────────────────────────────────────────────────────────
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_OUTPUT_DIR = _PROJECT_ROOT / "pipelines" / "output"

# ── configuration ────────────────────────────────────────────────────────
ANOMALY_MOM_THRESHOLD_UP = 1.5     # flag if MoM growth > +150 %
ANOMALY_MOM_THRESHOLD_DOWN = -0.80  # flag if MoM growth < -80 %
DEC_SURGE_WEIGHT = 0.5              # weight for Dec surge months (Jnah, MSC)
DEC_PARTIAL_WEIGHT = 0.0            # weight for Conut main Dec (partial)
TYRE_OCT_SPIKE_WEIGHT = 0.5         # weight for Conut-Tyre Oct spike


# ── data container returned to downstream ────────────────────────────────
@dataclass
class BranchSeries:
    """All data needed to forecast one branch."""
    branch: str
    # clean series (anomalous months removed)
    months_clean: list[int]          # month_num values
    revenue_clean: list[float]       # corresponding revenue
    # dec-weighted series (anomalies included with reduced weight)
    months_dec: list[int]
    revenue_dec: list[float]
    weights_dec: list[float]         # per-value sample weight
    # metadata
    n_clean: int = 0
    volatility_clean: float = 0.0    # computed on clean series only
    volatility_full: float = 0.0     # from feat_branch_month (full series)
    anomaly_flags: dict = field(default_factory=dict)  # month_num → anomaly_type
    last_clean_month_num: int = 0
    last_clean_month_name: str = ""
    last_clean_revenue: float = 0.0
    is_partial_history: bool = False
    has_delivery: bool = False
    has_table: bool = False
    has_takeaway: bool = False
    beverage_share: float = 0.0
    december_anomaly_flag: str = "none"  # for output column
    last_data_month_num: int = 0         # last month in FULL data (for forecast start)


_MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


def _load_dataframes() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load the three input CSVs."""
    sales = pd.read_csv(_OUTPUT_DIR / "monthly_sales.csv")
    feats = pd.read_csv(_OUTPUT_DIR / "feat_branch_month.csv")
    dims  = pd.read_csv(_OUTPUT_DIR / "dim_branch.csv")
    return sales, feats, dims


def _compute_mom_growth(revenues: list[float]) -> list[float | None]:
    """Month-over-month growth rates.  First element is None."""
    out: list[float | None] = [None]
    for i in range(1, len(revenues)):
        prev = revenues[i - 1]
        if prev == 0:
            out.append(None)
        else:
            out.append((revenues[i] - prev) / prev)
    return out


def _detect_anomalies(
    months: list[int],
    revenues: list[float],
    branch: str,
) -> dict[int, str]:
    """Return {month_num: anomaly_type} for flagged months."""
    flags: dict[int, str] = {}
    growth = _compute_mom_growth(revenues)

    for idx, (m, g) in enumerate(zip(months, growth)):
        if g is None:
            continue

        # Conut main December — partial month (drops > 80 %)
        if branch == "Conut" and m == 12 and g <= ANOMALY_MOM_THRESHOLD_DOWN:
            flags[m] = "likely_partial_month"
        # December surges for Jnah / MSC
        elif m == 12 and g >= ANOMALY_MOM_THRESHOLD_UP:
            flags[m] = "potential_surge"
        # Conut-Tyre October spike
        elif branch == "Conut - Tyre" and m == 10 and g >= ANOMALY_MOM_THRESHOLD_UP:
            flags[m] = "potential_spike"

    return flags


def _volatility_of_growth(revenues: list[float]) -> float:
    """Expanding std of MoM growth rates (same formula as features.py)."""
    growth = _compute_mom_growth(revenues)
    clean = [g for g in growth if g is not None]
    if len(clean) < 2:
        return 0.0
    return float(np.std(clean, ddof=1))


def _build_branch_series(
    branch: str,
    sales_branch: pd.DataFrame,
    feats_branch: pd.DataFrame,
    dims_row: pd.Series | None,
) -> BranchSeries:
    """Build a BranchSeries for one branch."""

    # sort by month_num
    sales_branch = sales_branch.sort_values("month_num").reset_index(drop=True)
    months_all = sales_branch["month_num"].tolist()
    revenue_all = sales_branch["revenue"].tolist()

    # anomaly detection
    anomaly_flags = _detect_anomalies(months_all, revenue_all, branch)

    # ── clean series (exclude anomalous months) ──────────────────────────
    months_clean, revenue_clean = [], []
    for m, r in zip(months_all, revenue_all):
        if m not in anomaly_flags:
            months_clean.append(m)
            revenue_clean.append(r)

    # ── december-weighted series ─────────────────────────────────────────
    months_dec, revenue_dec, weights_dec = [], [], []
    for m, r in zip(months_all, revenue_all):
        atype = anomaly_flags.get(m)
        if atype == "likely_partial_month":
            w = DEC_PARTIAL_WEIGHT
        elif atype == "potential_surge":
            w = DEC_SURGE_WEIGHT
        elif atype == "potential_spike":
            w = TYRE_OCT_SPIKE_WEIGHT
        else:
            w = 1.0
        # skip months with weight 0 entirely (they add nothing)
        if w > 0:
            months_dec.append(m)
            revenue_dec.append(r)
            weights_dec.append(w)

    # ── volatility (on clean series) ─────────────────────────────────────
    vol_clean = _volatility_of_growth(revenue_clean)

    # full-series volatility from feat_branch_month (last row)
    vol_full = 0.0
    if not feats_branch.empty:
        last_vol = feats_branch.sort_values("month_num").iloc[-1].get("volatility")
        if pd.notna(last_vol):
            vol_full = float(last_vol)

    # ── metadata from dim_branch ─────────────────────────────────────────
    has_delivery = bool(dims_row["has_delivery"]) if dims_row is not None else False
    has_table = bool(dims_row["has_table"]) if dims_row is not None else False
    has_takeaway = bool(dims_row["has_takeaway"]) if dims_row is not None else False

    bev_share = 0.0
    if not feats_branch.empty:
        bs = feats_branch.iloc[0].get("beverage_share")
        if pd.notna(bs):
            bev_share = float(bs)

    is_partial = bool(sales_branch["is_partial_history"].iloc[0])

    # december anomaly flag for output
    dec_flag = "none"
    if 12 in anomaly_flags:
        dec_flag = anomaly_flags[12]

    # last clean month
    if months_clean:
        last_m = months_clean[-1]
        last_r = revenue_clean[-1]
    else:
        last_m = months_all[-1]
        last_r = revenue_all[-1]

    # last month in the FULL data (for forecast start point)
    last_data_m = months_all[-1] if months_all else 12

    return BranchSeries(
        branch=branch,
        months_clean=months_clean,
        revenue_clean=revenue_clean,
        months_dec=months_dec,
        revenue_dec=revenue_dec,
        weights_dec=weights_dec,
        n_clean=len(months_clean),
        volatility_clean=vol_clean,
        volatility_full=vol_full,
        anomaly_flags=anomaly_flags,
        last_clean_month_num=last_m,
        last_clean_month_name=_MONTH_NAMES.get(last_m, f"Month {last_m}"),
        last_clean_revenue=last_r,
        is_partial_history=is_partial,
        has_delivery=has_delivery,
        has_table=has_table,
        has_takeaway=has_takeaway,
        beverage_share=bev_share,
        december_anomaly_flag=dec_flag,
        last_data_month_num=last_data_m,
    )


# ── public API ───────────────────────────────────────────────────────────

def prepare_all() -> dict[str, BranchSeries]:
    """
    Load data -> flag anomalies -> return {branch_name: BranchSeries}.
    """
    sales, feats, dims = _load_dataframes()
    branches = sorted(sales["branch"].unique())
    result: dict[str, BranchSeries] = {}

    for b in branches:
        s_b = sales[sales["branch"] == b].copy()
        f_b = feats[feats["branch"] == b].copy()

        dims_match = dims[dims["canonical_branch_name"] == b]
        d_row = dims_match.iloc[0] if not dims_match.empty else None

        result[b] = _build_branch_series(b, s_b, f_b, d_row)

    return result


# ── quick sanity print ───────────────────────────────────────────────────
if __name__ == "__main__":
    data = prepare_all()
    for name, bs in data.items():
        print(f"\n{'='*60}")
        print(f"Branch: {name}")
        print(f"  Clean months:  {bs.months_clean}  ({bs.n_clean} pts)")
        print(f"  Clean revenue: {[f'{r:,.0f}' for r in bs.revenue_clean]}")
        print(f"  Volatility (clean): {bs.volatility_clean:.4f}")
        print(f"  Volatility (full):  {bs.volatility_full:.4f}")
        print(f"  Anomalies: {bs.anomaly_flags}")
        print(f"  Dec weighted months:  {bs.months_dec}")
        print(f"  Dec weighted weights: {bs.weights_dec}")
        print(f"  December flag: {bs.december_anomaly_flag}")
        print(f"  Last clean: {bs.last_clean_month_name} = {bs.last_clean_revenue:,.0f}")
        print(f"  Partial history: {bs.is_partial_history}")
