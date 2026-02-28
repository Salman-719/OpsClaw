"""
Demand Forecast — Phase 2: Estimators
======================================
Four simple estimators.  Each takes a revenue series and returns
a list of point-estimates for *periods* months ahead.

- naive_forecast:      last value repeated
- wma_forecast:        weighted moving average of last k values
- linear_forecast:     OLS on month_num → revenue, extrapolated
- similarity_forecast: transfer growth from a reference branch (fallback)
"""

from __future__ import annotations

import numpy as np

# ── configuration ────────────────────────────────────────────────────────
WMA_WEIGHTS = [0.5, 0.3, 0.2]
MIN_MONTHS_FOR_LINEAR = 3


# ──────────────────────────────────────────────────────────────────────────
def naive_forecast(
    revenues: list[float],
    periods: int = 1,
) -> list[float]:
    """Next month = last observed value, repeated for *periods* months."""
    if not revenues:
        return [0.0] * periods
    last = revenues[-1]
    return [last] * periods


# ──────────────────────────────────────────────────────────────────────────
def wma_forecast(
    revenues: list[float],
    periods: int = 1,
    weights: list[float] | None = None,
) -> list[float]:
    """
    Weighted moving average of the last len(weights) values, projected
    forward.  If the series is shorter than the weight window, weights are
    re-normalised to fit the available data.
    """
    if not revenues:
        return [0.0] * periods

    w = list(weights or WMA_WEIGHTS)

    # trim weights to available data length
    k = min(len(w), len(revenues))
    w = w[:k]
    # normalise so they sum to 1
    ws = sum(w)
    w = [wi / ws for wi in w]

    # compute WMA once — then repeat for all periods (no information to
    # update iteratively with such sparse data)
    tail = revenues[-k:]
    wma = sum(vi * wi for vi, wi in zip(tail, w))
    return [wma] * periods


# ──────────────────────────────────────────────────────────────────────────
def linear_forecast(
    months: list[int],
    revenues: list[float],
    periods: int = 1,
) -> list[float]:
    """
    OLS:  month_num → revenue.   Extrapolate for future months.
    Falls back to naïve if fewer than MIN_MONTHS_FOR_LINEAR points.
    """
    if len(months) < MIN_MONTHS_FOR_LINEAR or len(revenues) < MIN_MONTHS_FOR_LINEAR:
        return naive_forecast(revenues, periods)

    x = np.array(months, dtype=float)
    y = np.array(revenues, dtype=float)

    # OLS:  y = slope * x + intercept
    n = len(x)
    x_mean = x.mean()
    y_mean = y.mean()
    slope = ((x * y).sum() - n * x_mean * y_mean) / ((x**2).sum() - n * x_mean**2)
    intercept = y_mean - slope * x_mean

    last_month = int(x[-1])
    result = []
    for p in range(1, periods + 1):
        future_month = last_month + p
        pred = slope * future_month + intercept
        # floor at zero — demand cannot be negative
        result.append(max(0.0, float(pred)))
    return result


# ──────────────────────────────────────────────────────────────────────────
def weighted_linear_forecast(
    months: list[int],
    revenues: list[float],
    weights: list[float],
    periods: int = 1,
) -> list[float]:
    """
    Weighted OLS:  month_num → revenue using sample weights.
    Used for the december-sensitive scenario where anomalous months get
    reduced weight.
    """
    if len(months) < MIN_MONTHS_FOR_LINEAR:
        return naive_forecast(revenues, periods)

    x = np.array(months, dtype=float)
    y = np.array(revenues, dtype=float)
    w = np.array(weights, dtype=float)

    # weighted means
    w_sum = w.sum()
    x_w = (w * x).sum() / w_sum
    y_w = (w * y).sum() / w_sum

    slope = ((w * x * y).sum() - w_sum * x_w * y_w) / (
        (w * x**2).sum() - w_sum * x_w**2
    )
    intercept = y_w - slope * x_w

    last_month = int(x[-1])
    result = []
    for p in range(1, periods + 1):
        future_month = last_month + p
        pred = slope * future_month + intercept
        result.append(max(0.0, float(pred)))
    return result


# ──────────────────────────────────────────────────────────────────────────
def similarity_forecast(
    target_last_revenue: float,
    reference_revenues: list[float],
    revenue_ratio: float,
    periods: int = 1,
) -> list[float]:
    """
    Transfer the most-recent growth rate of *reference_branch* to
    *target_branch*, scaled by *revenue_ratio*.

    This is a **fallback** — only called when the target branch has
    fewer than SIMILARITY_ACTIVATION_THRESHOLD clean months.
    """
    if len(reference_revenues) < 2 or target_last_revenue <= 0:
        return [target_last_revenue] * periods

    ref_growth = (reference_revenues[-1] - reference_revenues[-2]) / reference_revenues[-2]

    results = []
    current = target_last_revenue
    for _ in range(periods):
        current = max(0.0, current * (1 + ref_growth))
        results.append(current)
    return results
