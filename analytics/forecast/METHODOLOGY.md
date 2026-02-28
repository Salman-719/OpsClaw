# Demand Forecast — Methodology & Technical Reference

## 1. Problem Statement

Forecast next-month demand per branch to support inventory and supply chain decisions. The data has **4–5 months of history per branch** with **high volatility** and **anomalous December behavior**. This is a tiny-sample estimation problem, not a standard time-series forecasting problem.

---

## 2. Data Pipeline

### 2.1 Inputs

| File | Rows | Role |
|---|---|---|
| `monthly_sales.csv` | 19 | Primary time-series: branch × month × revenue |
| `feat_branch_month.csv` | 19 | Pre-computed features: MA3, MoM growth, volatility, channel/beverage shares |
| `dim_branch.csv` | 4 | Branch metadata: channel flags, months of data |

### 2.2 Preparation (`prepare.py`)

For each branch, the module:

1. **Sorts** by `month_num` to get a chronological revenue series.
2. **Computes MoM growth** for every consecutive pair.
3. **Flags anomalies** when growth exceeds thresholds:
   - Conut Dec: MoM = −95% → `likely_partial_month` (data cutoff, not real demand drop)
   - Conut Jnah Dec: MoM = +204% → `potential_surge` (holiday or seasonal spike)
   - Main Street Coffee Dec: MoM = +162% → `potential_surge`
   - Conut-Tyre Oct: MoM = +372% → `potential_spike` (unexplained single-month outlier)
4. **Produces two series per branch:**
   - **`series_clean`** — anomalous months removed entirely. Used for the **base** scenario.
   - **`series_dec_weighted`** — anomalous months kept but with reduced sample weight. Surge months get weight 0.5; Conut Dec (partial) gets weight 0.0 (effectively excluded in both scenarios). Used for the **december_sensitive** scenario.
5. **Computes clean volatility** — standard deviation of MoM growth rates on the clean series only, which avoids inflated volatility from outliers.

### 2.3 Output Container: `BranchSeries`

A dataclass carrying everything downstream needs:

```
branch, months_clean, revenue_clean, months_dec, revenue_dec, weights_dec,
n_clean, volatility_clean, volatility_full, anomaly_flags,
last_clean_month_num, last_clean_month_name, last_clean_revenue,
is_partial_history, has_delivery, has_table, has_takeaway,
beverage_share, december_anomaly_flag, last_data_month_num
```

---

## 3. Estimators (`estimators.py`)

Three core estimators run for every branch/scenario. A fourth activates only when data is scarce.

### 3.1 Naïve

```
forecast(t+1) = revenue(t)
```

Repeats the last observed value for all future periods. Zero assumptions, zero overfitting. Serves as the conservative anchor.

### 3.2 Weighted Moving Average (WMA-3)

```
forecast(t+1) = 0.5 × revenue(t) + 0.3 × revenue(t-1) + 0.2 × revenue(t-2)
```

Weights: `[0.5, 0.3, 0.2]` — most recent month gets 50%. If fewer than 3 data points, weights are re-normalised to fit available data. Produces a smoothed level estimate. Same value for all future periods (no extrapolation).

### 3.3 Linear OLS

```
revenue = slope × month_num + intercept
```

Ordinary least squares regression on month number → revenue. Extrapolates forward, so P1 ≠ P2 ≠ P3. This is the only estimator that captures trend direction. Requires at least 3 data points; falls back to naïve otherwise.

For the **december_sensitive** scenario, a **weighted OLS** variant is used — anomalous months influence the fit less via their reduced sample weight.

### 3.4 Similarity Fallback

```
forecast(t+1) = target_last_revenue × (1 + reference_branch_growth)
```

Transfers the most recent growth rate from a similar branch, scaled by the revenue ratio. **Activation rules:**

- Only fires when `n_clean < 4` (currently: Main Street Coffee base scenario with 3 clean points).
- Uses Conut Jnah as the reference (similar profile: table-only, December surge, comparable beverage share).
- Gets weighted at 0.5× in the ensemble (half the influence of core estimators).

---

## 4. Ensemble (`ensemble.py`)

### 4.1 Point Estimate

For each period, the three (or four) estimator outputs are combined via **weighted median**:

- Core estimators: weight = 1.0 each.
- Similarity (when active): weight = 0.5.

The weighted median is more robust to a single wild estimator than a simple mean.

### 4.2 Confidence Bands

```
capped_volatility = min(historical_volatility, 0.75)
p25 = 25th percentile of estimator outputs
p75 = 75th percentile of estimator outputs
band_low  = max(0, p25 × (1 − capped_volatility))
band_high = p75 × (1 + capped_volatility)
```

**Capping at 0.75** prevents the lower bound from going negative when volatility exceeds 1.0 (which it does for Conut-Tyre at 1.97 and MSC at 2.61). The base band comes from estimator spread; the capped volatility widens it to reflect historical instability.

**Rule: lower bound is always ≥ 0.** Demand cannot be negative.

### 4.3 Confidence Level

| Condition | Label |
|---|---|
| n_clean ≥ 5 and volatility < 0.5 | `medium` |
| n_clean ≥ 4 and volatility < 1.0 | `low-medium` |
| n_clean < 4 or volatility ≥ 1.0 | `low` |

Never `high` — the data is too sparse for that.

### 4.4 Forecast Stability Score

A 0–100 composite from four equally-weighted components (each 0–25):

| Component | 25 (best) | 0 (worst) | Formula |
|---|---|---|---|
| **Data quantity** | n_clean ≥ 5 | n_clean ≤ 2 | `min(25, (n_clean − 2) × 25/3)` |
| **Volatility** | vol ≤ 0.2 | vol ≥ 1.5 | `max(0, 25 × (1 − vol/1.5))` |
| **Estimator agreement** | spread ≤ 0% | spread ≥ 100% | `max(0, 25 × (1 − disagreement))` |
| **Anomaly absence** | No anomalies | Adjacent anomaly | 25 / 10 / 0 |

**Labels:**
- **≥ 60 → `stable`** — reasonable for firm planning.
- **30–59 → `cautious`** — use for directional guidance, plan for wider variance.
- **< 30 → `unstable`** — directional only, not actionable for commitments.

**Why this matters:** A single number tells the ops planner "how much can I trust this row?" without needing to understand volatility, disagreement, or anomaly flags individually.

---

## 5. Dual-Scenario Design

Every branch produces two labeled scenarios:

| Scenario | Series used | Purpose |
|---|---|---|
| **`base`** | Clean (anomalies removed) | "Normal replenishment" — conservative, trend-following |
| **`december_sensitive`** | Dec-weighted (anomalies at 0.5 weight) | "Surge-prepared" — what to plan for if December-like demand recurs |

**Special case — Conut main:** December was a partial-month data cutoff (−95%), not a demand event. It gets weight = 0.0 in both scenarios, so base and december_sensitive are identical. The `notes` column explains this.

**Why dual scenarios instead of one number:** Operations needs two distinct planning postures — "stock conservatively" vs. "prepare surge capacity." A single forecast with a wide band doesn't give that decision frame.

---

## 6. Output Schema

### `demand_forecast_all.csv` — 24 rows

| Column | Type | Description |
|---|---|---|
| `branch` | str | Branch name |
| `scenario` | str | `base` or `december_sensitive` |
| `forecast_period` | int | 1 (primary), 2, 3 (extensions) |
| `is_primary` | bool | True for period 1 only |
| `forecast_month` | str | "January 2026", "February 2026", "March 2026" |
| `demand_index_forecast` | float | Ensemble median (scaled units) |
| `expected_change_vs_last_clean_month` | float | % change vs last non-anomalous month |
| `relative_band_low` | float | Lower bound (always ≥ 0) |
| `relative_band_high` | float | Upper bound |
| `band_width_pct` | float | (high − low) / forecast |
| `naive_estimate` | float | Naïve estimator output |
| `wma3_estimate` | float | WMA-3 estimator output |
| `linear_estimate` | float | Linear OLS estimator output |
| `similarity_estimate` | float | Fallback estimator (null if n_clean ≥ 4) |
| `method` | str | Always `ensemble_median` |
| `confidence_level` | str | `low` / `low-medium` / `medium` |
| `forecast_stability_score` | int | 0–100 composite |
| `forecast_stability_label` | str | `stable` / `cautious` / `unstable` |
| `n_months_used` | int | Data points in the series for this scenario |
| `last_clean_month` | str | Last non-anomalous month name |
| `december_anomaly_flag` | str | `likely_partial_month` / `potential_surge` / `none` |
| `notes` | str | Warnings and caveats |

### `forecast_metadata.json`

Run timestamp, full parameter set, and per-branch anomaly flags. Enables reproducibility — any future run with the same parameters on the same data will produce the same output.

---

## 7. Parameters

All tuneable constants and their locations:

| Parameter | Default | File | Effect |
|---|---|---|---|
| `ANOMALY_MOM_THRESHOLD_UP` | 1.5 | prepare.py | MoM growth above this → flagged as anomaly |
| `ANOMALY_MOM_THRESHOLD_DOWN` | −0.80 | prepare.py | MoM growth below this → flagged as anomaly |
| `DEC_SURGE_WEIGHT` | 0.5 | prepare.py | Sample weight for December surge months in dec-sensitive scenario |
| `DEC_PARTIAL_WEIGHT` | 0.0 | prepare.py | Sample weight for Conut Dec (= excluded) |
| `TYRE_OCT_SPIKE_WEIGHT` | 0.5 | prepare.py | Sample weight for Conut-Tyre October spike |
| `WMA_WEIGHTS` | [0.5, 0.3, 0.2] | estimators.py | Recency weights for WMA-3 |
| `MIN_MONTHS_FOR_LINEAR` | 3 | estimators.py | Minimum points for OLS; falls back to naïve below this |
| `CAPPED_VOLATILITY_MAX` | 0.75 | ensemble.py | Volatility cap for band construction |
| `SIMILARITY_ACTIVATION_THRESHOLD` | 4 | ensemble.py | Similarity only fires when n_clean < this |
| `SIMILARITY_WEIGHT_FACTOR` | 0.5 | ensemble.py | Similarity estimator weight relative to core (0.5 = half) |
| `PRIMARY_PERIODS` | 1 | ensemble.py | Months in the primary forecast |
| `EXTENSION_PERIODS` | 2 | ensemble.py | Additional low-confidence extension months |

---

## 8. Per-Branch Summary

### Conut (main)

- **Clean data:** 4 months (Aug–Nov). Dec excluded (partial-month artifact).
- **Trend:** Steady growth decelerating (+42% → +45% → +19%).
- **Base forecast (Jan):** ~1.35B. Band: [1.01B, 1.71B]. **Stable (61).**
- **Dec-sensitive:** Identical (Dec weight = 0).
- **This is the most reliable forecast in the fleet.**

### Conut - Tyre

- **Clean data:** 4 months (Aug, Sep, Nov, Dec). Oct excluded (spike).
- **Pattern:** Volatile — spike then stabilisation around 1.0B.
- **Base forecast (Jan):** ~1.02B. Band: [0.22B, 2.04B]. **Cautious (46).**
- **Dec-sensitive:** ~1.45B (Oct re-included at 0.5 weight pulls trend up).
- **Wide bands reflect genuine uncertainty.**

### Conut Jnah

- **Clean data:** 4 months (Aug–Nov). Dec excluded (3× surge).
- **Trend:** Steady growth (+96% → +10% → +21%).
- **Base forecast (Jan):** ~0.95B. Band: [0.46B, 1.55B]. **Cautious (58).**
- **Dec-sensitive:** ~2.32B. Band: [0.45B, 4.55B]. **Cautious (52).**
- **The gap between scenarios is the "normal vs. surge" decision frame.**

### Main Street Coffee

- **Clean data:** 3 months (Sep–Nov). Dec excluded (surge). Only 4 months total.
- **Similarity fallback active** (Conut Jnah as reference).
- **Base forecast (Jan):** ~1.17B. Band: [0.26B, 2.63B]. **Unstable (18).**
- **Dec-sensitive:** ~3.07B. Band: [0.56B, 5.57B]. **Cautious (35).**
- **Least reliable — use for directional awareness only.**

---

## 9. Known Limitations

1. **4–5 data points per branch.** Output is a "best structured estimate," not a statistically validated prediction.
2. **December is anomalous for all branches** in different directions. Dual scenarios handle this but don't resolve the underlying ambiguity.
3. **All values are in scaled/arbitrary units.** Do not interpret as currency.
4. **Naïve and WMA are flat across periods.** P2/P3 forecasts may understate trend — only linear changes across periods.
5. **MSC uses different estimator sets per scenario.** Base (3 points) triggers similarity; dec-sensitive (4 points) doesn't. Scenarios aren't perfectly comparable.
6. **Band widths are wide** (0.5–2.0× for most branches). Only Conut base is tight enough for firm inventory commitments.
7. **No daily/weekly granularity.** Intra-month planning not possible.
8. **No product-level forecasting.** Cannot predict which items will be in demand.
9. **Channel-data inconsistency.** `dim_branch` says Jnah/MSC have no delivery, but `customer_orders.csv` has records for all 4 branches.
10. **Branch similarity is narrative, not statistical.** With only 4 branches, cosine similarity is fragile.

---

## 10. Validation Approach

| Method | What it checks |
|---|---|
| **Leave-one-out backtest** | Hold out last clean month, forecast it, measure error. Repeatable for second-to-last. |
| **Estimator disagreement** | `(max − min) / median` across core estimators. Feeds into stability score. |
| **Historical range check** | Forecast must fall within [0.5×, 2.0×] of clean historical range. Violations get a warning in `notes`. |
| **Branch share ranking** | Forecasted demand ranking should be consistent with historical hierarchy. |

No reconciliation against `avg_sales_menu` — that file has no time dimension and cannot validate monthly forecasts.
