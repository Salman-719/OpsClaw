"""
Demand Forecast — Phase 3: Ensemble + Confidence
=================================================
Combines estimator outputs into a single forecast per branch per scenario.
Computes confidence bands (capped volatility), stability score, and labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .prepare import BranchSeries
from .estimators import (
    naive_forecast,
    wma_forecast,
    linear_forecast,
    weighted_linear_forecast,
    similarity_forecast,
)

# ── configuration ────────────────────────────────────────────────────────
CAPPED_VOLATILITY_MAX = 0.75
SIMILARITY_ACTIVATION_THRESHOLD = 4   # n_clean < this → activate similarity
SIMILARITY_WEIGHT_FACTOR = 0.5        # similarity gets 0.5× weight of core
PRIMARY_PERIODS = 1
EXTENSION_PERIODS = 2
TOTAL_PERIODS = PRIMARY_PERIODS + EXTENSION_PERIODS

_MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


# ── dataclass for one forecast row ───────────────────────────────────────
@dataclass
class ForecastRow:
    branch: str
    scenario: str                        # "base" | "december_sensitive"
    forecast_period: int                  # 1, 2, 3
    is_primary: bool
    forecast_month: str
    demand_index_forecast: float
    expected_change_vs_last_clean_month: float
    relative_band_low: float
    relative_band_high: float
    band_width_pct: float
    naive_estimate: float
    wma3_estimate: float
    linear_estimate: float
    similarity_estimate: Optional[float]
    method: str
    confidence_level: str
    forecast_stability_score: int
    forecast_stability_label: str
    # stability breakdown (each 0-25)
    stability_data_qty: int = 0
    stability_volatility: int = 0
    stability_agreement: int = 0
    stability_anomaly: int = 0
    n_months_used: int = 0
    last_clean_month: str = ""
    december_anomaly_flag: str = "none"
    notes: str = ""
    explanation: str = ""                  # human-readable reasoning


# ── helpers ──────────────────────────────────────────────────────────────

def _weighted_median(values: list[float], weights: list[float]) -> float:
    """Weighted median — sorts by value and finds the crossing point."""
    if not values:
        return 0.0
    pairs = sorted(zip(values, weights))
    cum_w = 0.0
    total = sum(weights)
    for v, w in pairs:
        cum_w += w
        if cum_w >= total / 2:
            return v
    return pairs[-1][0]


def _percentile(values: list[float], pct: float) -> float:
    """Simple percentile (linear interpolation)."""
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(s):
        return s[-1]
    return s[f] + (k - f) * (s[c] - s[f])


def _compute_confidence_level(n_clean: int, volatility: float) -> str:
    if n_clean >= 5 and volatility < 0.5:
        return "medium"
    if n_clean >= 4 and volatility < 1.0:
        return "low-medium"
    return "low"


def _compute_stability_score(
    n_clean: int,
    volatility: float,
    estimator_disagreement: float,
    has_anomaly_adjacent: bool,
) -> tuple[int, str, int, int, int, int]:
    """
    0-100 composite from 4 components (each 0-25).
    Returns (score, label, dq, vol_score, agree, anom).
    """
    # 1) data quantity: 0 at n=2, 25 at n=5+
    dq = min(25, max(0, int((n_clean - 2) * 25 / 3)))

    # 2) volatility: 25 at vol≤0.2, 0 at vol≥1.5
    vol_score = max(0, int(25 * (1 - volatility / 1.5)))

    # 3) estimator agreement: 25 at disagreement=0, 0 at disagreement≥1.0
    agree = max(0, int(25 * (1 - min(estimator_disagreement, 1.0))))

    # 4) anomaly absence: 25 if none, 10 if flagged but handled, 0 if adjacent
    if not has_anomaly_adjacent:
        anom = 25
    else:
        anom = 10  # flagged but handled by dual-scenario

    score = dq + vol_score + agree + anom
    score = max(0, min(100, score))

    if score >= 60:
        label = "stable"
    elif score >= 30:
        label = "cautious"
    else:
        label = "unstable"

    return score, label, dq, vol_score, agree, anom


def _sanity_notes(
    forecast: float,
    revenue_clean: list[float],
    is_partial_history: bool,
    scenario: str,
) -> list[str]:
    """Generate any warning notes."""
    notes: list[str] = []

    if is_partial_history:
        notes.append("is_partial_history=True — fewer months than other branches")

    if revenue_clean:
        hist_min = min(revenue_clean)
        hist_max = max(revenue_clean)
        if forecast < 0.5 * hist_min:
            notes.append(f"WARN: forecast below 0.5× historical min ({hist_min:,.0f})")
        if forecast > 2.0 * hist_max:
            notes.append(f"WARN: forecast above 2.0× historical max ({hist_max:,.0f})")

    return notes


# ── explanation builder ──────────────────────────────────────────────────

def _fmt(v: float) -> str:
    """Format large numbers readably."""
    if abs(v) >= 1e9:
        return f"{v / 1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"{v / 1e6:.0f}M"
    return f"{v:,.0f}"


def _build_explanation(
    *,
    bs: BranchSeries,
    scenario: str,
    p: int,
    forecast_val: float,
    vals: list[float],
    naive_est_p: float,
    wma_est_p: float,
    lin_est_p: float,
    sim_est_p: float | None,
    use_similarity: bool,
    n_used: int,
    volatility: float,
    capped_vol: float,
    band_low: float,
    band_high: float,
    stab_score: int,
    stab_label: str,
    s_dq: int,
    s_vol: int,
    s_agree: int,
    s_anom: int,
    disagreement: float,
) -> str:
    """Build a human-readable explanation for one forecast row."""

    parts: list[str] = []

    # ── 1. Data basis ────────────────────────────────────────────────────
    if scenario == "base":
        parts.append(
            f"Based on {n_used} clean monthly data points "
            f"(anomalous months excluded)."
        )
    else:
        parts.append(
            f"Based on {n_used} monthly data points "
            f"(anomalous months included with reduced weight)."
        )

    # ── 2. Anomaly context ───────────────────────────────────────────────
    if bs.anomaly_flags:
        for m, atype in bs.anomaly_flags.items():
            month_name = _MONTH_NAMES.get(m, f"Month {m}")
            if atype == "likely_partial_month":
                parts.append(
                    f"{month_name} was flagged as a likely partial month "
                    f"(revenue dropped 95%) and is excluded from both scenarios."
                )
            elif atype == "potential_surge":
                if scenario == "base":
                    parts.append(
                        f"{month_name} showed a potential surge and is "
                        f"excluded in this base scenario."
                    )
                else:
                    parts.append(
                        f"{month_name} showed a potential surge and is "
                        f"included here with 50% weight."
                    )
            elif atype == "potential_spike":
                if scenario == "base":
                    parts.append(
                        f"{month_name} showed an unexplained spike and is "
                        f"excluded in this base scenario."
                    )
                else:
                    parts.append(
                        f"{month_name} showed an unexplained spike and is "
                        f"included here with 50% weight."
                    )

    # ── 3. Estimator reasoning ───────────────────────────────────────────
    est_lines = []
    est_lines.append(f"Naive (last value repeated) = {_fmt(naive_est_p)}")
    est_lines.append(f"WMA-3 (weighted avg of last 3 months) = {_fmt(wma_est_p)}")
    est_lines.append(f"Linear OLS (trend extrapolation) = {_fmt(lin_est_p)}")
    if use_similarity and sim_est_p is not None:
        est_lines.append(
            f"Similarity fallback (growth transferred from {bs.branch}'s "
            f"reference branch, weighted at 0.5x) = {_fmt(sim_est_p)}"
        )
    parts.append("Estimators: " + "; ".join(est_lines) + ".")

    # ── 4. How the forecast was chosen ───────────────────────────────────
    parts.append(
        f"The forecast ({_fmt(forecast_val)}) is the weighted median of "
        f"these {len(vals)} estimators."
    )

    # ── 5. Band explanation ──────────────────────────────────────────────
    parts.append(
        f"Confidence band [{_fmt(band_low)}, {_fmt(band_high)}] is built from "
        f"the estimator spread (p25-p75) widened by capped volatility "
        f"({volatility:.2f} capped to {capped_vol:.2f}). "
        f"Band width = {((band_high - band_low) / forecast_val * 100):.0f}% of forecast."
        if forecast_val > 0 else
        f"Confidence band [{_fmt(band_low)}, {_fmt(band_high)}]."
    )

    # ── 6. Stability score breakdown ─────────────────────────────────────
    parts.append(
        f"Stability score {stab_score}/100 ({stab_label}): "
        f"data quantity {s_dq}/25, "
        f"volatility {s_vol}/25, "
        f"estimator agreement {s_agree}/25 "
        f"(disagreement={disagreement:.0%}), "
        f"anomaly {s_anom}/25."
    )

    # ── 7. Period caveat ─────────────────────────────────────────────────
    if p == 1:
        parts.append("This is the primary 1-month-ahead forecast — the most credible output.")
    else:
        parts.append(
            f"This is a period-{p} extension (low confidence). "
            f"Use for directional awareness only, not firm planning."
        )

    return " ".join(parts)


# ── main ensemble logic ─────────────────────────────────────────────────

def _forecast_scenario(
    bs: BranchSeries,
    scenario: str,
    months: list[int],
    revenues: list[float],
    weights: list[float] | None,
    n_used: int,
    volatility: float,
    reference_bs: BranchSeries | None,
) -> list[ForecastRow]:
    """Produce forecast rows for one branch + one scenario."""

    periods = TOTAL_PERIODS
    # Always forecast from the last month in the FULL data, not the clean
    # subset.  All branches have data through Dec 2025 → forecast starts Jan 2026.
    last_month = bs.last_data_month_num

    # ── run core estimators ──────────────────────────────────────────────
    naive_est = naive_forecast(revenues, periods)
    wma_est   = wma_forecast(revenues, periods)

    if weights is not None and scenario == "december_sensitive":
        lin_est = weighted_linear_forecast(months, revenues, weights, periods)
    else:
        lin_est = linear_forecast(months, revenues, periods)

    # ── similarity fallback ──────────────────────────────────────────────
    sim_est: list[float | None] = [None] * periods
    use_similarity = (n_used < SIMILARITY_ACTIVATION_THRESHOLD) and (reference_bs is not None)

    if use_similarity and reference_bs is not None:
        ref_rev = reference_bs.revenue_clean
        if ref_rev and bs.last_clean_revenue > 0:
            ratio = bs.last_clean_revenue / (ref_rev[-1] if ref_rev[-1] else 1.0)
            sim_vals = similarity_forecast(
                bs.last_clean_revenue, ref_rev, ratio, periods
            )
            sim_est = sim_vals  # type: ignore[assignment]

    # ── build per-period rows ────────────────────────────────────────────
    rows: list[ForecastRow] = []
    for p_idx in range(periods):
        p = p_idx + 1  # 1-based period
        # Calculate calendar month and year for the forecast period
        future_month_num_abs = last_month + p
        fy = 2025 + (future_month_num_abs - 1) // 12
        fm = (future_month_num_abs - 1) % 12 + 1
        forecast_month_str = f"{_MONTH_NAMES.get(fm, f'Month {fm}')} {fy}"

        # collect estimator values for this period
        vals = [naive_est[p_idx], wma_est[p_idx], lin_est[p_idx]]
        wgts = [1.0, 1.0, 1.0]

        if use_similarity and sim_est[p_idx] is not None:
            vals.append(sim_est[p_idx])  # type: ignore[arg-type]
            wgts.append(SIMILARITY_WEIGHT_FACTOR)

        # ensemble median (weighted)
        forecast_val = _weighted_median(vals, wgts)

        # ── confidence band ──────────────────────────────────────────────
        capped_vol = min(volatility, CAPPED_VOLATILITY_MAX)
        p25 = _percentile(vals, 25)
        p75 = _percentile(vals, 75)
        band_low  = max(0.0, p25 * (1 - capped_vol))
        band_high = p75 * (1 + capped_vol)

        if forecast_val > 0:
            band_width = (band_high - band_low) / forecast_val
        else:
            band_width = 0.0

        # % change vs last clean month
        if bs.last_clean_revenue > 0:
            expected_change = (forecast_val - bs.last_clean_revenue) / bs.last_clean_revenue
        else:
            expected_change = 0.0

        # ── estimator disagreement ───────────────────────────────────────
        median_core = float(np.median(vals[:3]))
        if median_core > 0:
            disagreement = (max(vals[:3]) - min(vals[:3])) / median_core
        else:
            disagreement = 0.0

        # ── stability score ──────────────────────────────────────────────
        has_anomaly_adj = bool(bs.anomaly_flags)
        stab_score, stab_label, s_dq, s_vol, s_agree, s_anom = _compute_stability_score(
            n_used, volatility, disagreement, has_anomaly_adj
        )

        # ── confidence level ─────────────────────────────────────────────
        conf = _compute_confidence_level(n_used, volatility)

        # ── notes ────────────────────────────────────────────────────────
        notes_list = _sanity_notes(
            forecast_val, bs.revenue_clean, bs.is_partial_history, scenario
        )
        # Conut main: both scenarios identical
        if bs.branch == "Conut" and scenario == "december_sensitive":
            notes_list.append("scenarios identical — December excluded as partial month")

        # ── build explanation text ─────────────────────────────────────────
        explanation = _build_explanation(
            bs=bs, scenario=scenario, p=p,
            forecast_val=forecast_val, vals=vals,
            naive_est_p=naive_est[p_idx], wma_est_p=wma_est[p_idx],
            lin_est_p=lin_est[p_idx], sim_est_p=sim_est[p_idx],
            use_similarity=use_similarity, n_used=n_used,
            volatility=volatility, capped_vol=capped_vol,
            band_low=band_low, band_high=band_high,
            stab_score=stab_score, stab_label=stab_label,
            s_dq=s_dq, s_vol=s_vol, s_agree=s_agree, s_anom=s_anom,
            disagreement=disagreement,
        )

        rows.append(ForecastRow(
            branch=bs.branch,
            scenario=scenario,
            forecast_period=p,
            is_primary=(p == 1),
            forecast_month=forecast_month_str,
            demand_index_forecast=round(forecast_val, 2),
            expected_change_vs_last_clean_month=round(expected_change, 4),
            relative_band_low=round(band_low, 2),
            relative_band_high=round(band_high, 2),
            band_width_pct=round(band_width, 4),
            naive_estimate=round(naive_est[p_idx], 2),
            wma3_estimate=round(wma_est[p_idx], 2),
            linear_estimate=round(lin_est[p_idx], 2),
            similarity_estimate=round(sim_est[p_idx], 2) if sim_est[p_idx] is not None else None,
            method="ensemble_median",
            confidence_level=conf,
            forecast_stability_score=stab_score,
            forecast_stability_label=stab_label,
            stability_data_qty=s_dq,
            stability_volatility=s_vol,
            stability_agreement=s_agree,
            stability_anomaly=s_anom,
            n_months_used=n_used,
            last_clean_month=bs.last_clean_month_name,
            december_anomaly_flag=bs.december_anomaly_flag,
            notes="; ".join(notes_list) if notes_list else "",
            explanation=explanation,
        ))

    return rows


# ── public API ───────────────────────────────────────────────────────────

def ensemble_forecast(
    bs: BranchSeries,
    reference_bs: BranchSeries | None = None,
) -> list[ForecastRow]:
    """
    Produce forecast rows for one branch — BOTH scenarios.
    Returns 6 rows total (2 scenarios × 3 periods).
    """
    all_rows: list[ForecastRow] = []

    # ── Base scenario (clean series) ─────────────────────────────────────
    base_rows = _forecast_scenario(
        bs=bs,
        scenario="base",
        months=bs.months_clean,
        revenues=bs.revenue_clean,
        weights=None,
        n_used=bs.n_clean,
        volatility=bs.volatility_clean,
        reference_bs=reference_bs,
    )
    all_rows.extend(base_rows)

    # ── December-sensitive scenario (weighted series) ────────────────────
    dec_rows = _forecast_scenario(
        bs=bs,
        scenario="december_sensitive",
        months=bs.months_dec,
        revenues=bs.revenue_dec,
        weights=bs.weights_dec,
        n_used=len(bs.months_dec),
        volatility=bs.volatility_full if bs.volatility_full > 0 else bs.volatility_clean,
        reference_bs=reference_bs,
    )
    all_rows.extend(dec_rows)

    return all_rows
