# Demand Forecasting by Branch — Detailed Plan

## 1. Objective

Forecast demand per branch to support **inventory and supply chain decisions**.

The brief requires this to be operationally useful — not just a model metric. The output must tell a branch manager or ops planner "how much to expect next month" in relative terms, with honest uncertainty bounds.

**Forecast horizon:** The **primary output is a 1-month-ahead forecast** (January 2026). With only 4–5 data points per branch, a single-month forecast is the most credible planning signal. Months 2–3 (February–March 2026) are provided as **optional low-confidence scenario extensions** — useful for directional awareness but not for firm planning commitments.

---

## 2. Available Data — What We Actually Have

### 2.1 Primary Source: `monthly_sales.csv` (19 rows)

The **only time-series** in our data. One row per branch per month.

| branch | months | range | pattern |
|---|---|---|---|
| Conut | 5 | Aug–Dec 2025 | Steady growth Aug→Nov, then **Dec collapses to 5% of Nov** (partial month / data cutoff) |
| Conut - Tyre | 5 | Aug–Dec 2025 | Volatile — Oct spikes to 4.7× Sep, then drops. No clear trend |
| Conut Jnah | 5 | Aug–Dec 2025 | Steady growth Aug→Nov, then **Dec explodes to 3× Nov** (holiday surge or data anomaly) |
| Main Street Coffee | 4 | Sep–Dec 2025 | Growth curve — but Sep is tiny (145M), Dec is 3B. Very steep. Flagged `is_partial_history=True` |

**Actual values (scaled internal units):**

```
Conut:
  Aug:    554,074,783
  Sep:    784,385,377
  Oct:  1,137,352,241
  Nov:  1,351,165,728
  Dec:     67,887,513   ← ANOMALY: 5% of Nov

Conut - Tyre:
  Aug:    477,535,459
  Sep:    444,800,811
  Oct:  2,100,816,729   ← SPIKE: 4.7× Sep
  Nov:  1,129,526,810
  Dec:  1,024,205,946

Conut Jnah:
  Aug:    363,540,268
  Sep:    714,037,266
  Oct:    785,925,565
  Nov:    947,652,051
  Dec:  2,878,191,130   ← SPIKE: 3× Nov

Main Street Coffee:
  Sep:    145,842,540   ← Very low (likely opened recently)
  Oct:    920,588,160
  Nov:  1,171,534,376
  Dec:  3,074,216,294   ← Same Dec spike pattern as Conut Jnah
```

**Critical observation:** December is anomalous for ALL branches. Conut main drops 95%, while Jnah and MSC spike 200–300%. This is either:
- A real holiday/seasonal effect (Dec is high-demand for sweets businesses)
- A partial-month artifact for Conut main (data export cut off early)
- Both

This single observation fundamentally shapes the forecasting approach. We cannot naïvely extrapolate through December.

### 2.2 Pre-built Features: `feat_branch_month.csv` (19 rows)

Same 19 rows as monthly_sales, enriched with:

| Column | Description | Key values |
|---|---|---|
| `revenue_ma3` | 3-month moving average | Only populated from month 3 onwards (Oct+) |
| `mom_growth` | Month-over-month growth rate | Conut: +0.42, +0.45, +0.19, **-0.95**. Tyre: -0.07, **+3.72**, -0.46, -0.09. Jnah: +0.96, +0.10, +0.21, **+2.04**. MSC: **+5.31**, +0.27, **+1.62** |
| `volatility` | Expanding std of growth rates | Conut: 0.66. Tyre: 1.97. Jnah: 0.89. MSC: 2.61 |
| `channel_delivery_share` | Delivery % of branch revenue | Conut: 0.25%, Tyre: 3.85%, Jnah: NaN, MSC: NaN |
| `beverage_share` | Beverage % of product mix | Conut: 4.7%, Tyre: 4.4%, Jnah: 14.6%, MSC: 8.9% |

**Key insight:** volatility is very high across all branches (0.66–2.61). Any forecast must have wide confidence bands.

### 2.3 Supporting: `dim_branch.csv` (4 rows)

| branch | delivery | table | takeaway | months | attendance_data |
|---|---|---|---|---|---|
| Conut | ✓ | ✓ | ✓ | 5 | ✗ |
| Conut - Tyre | ✓ | ✗ | ✓ | 5 | ✓ |
| Conut Jnah | ✗ | ✓ | ✗ | 5 | ✓ |
| Main Street Coffee | ✗ | ✓ | ✗ | 4 | ✓ |

### 2.4 Supporting: `avg_sales_menu.csv` (7 rows)

Branch × channel aggregates. No time dimension. Useful for:
- Understanding channel mix (delivery vs table vs takeaway)
- Estimating per-customer ticket size by channel
- Cross-validating total revenue with monthly_sales

### 2.5 Supporting: `customer_orders.csv` (539 rows)

Delivery customers with `first_order`, `last_order`, `num_orders`, `total`. This is a **customer summary table**, not an order-level event log.

**⚠ Methodological correction:** Previously we derived "weekly order counts by branch" by grouping `last_order` timestamps by week. This is **not actual weekly order volume** — it is the count of customers whose most recent recorded order fell in that week (`weekly_last_order_events`). That metric tells us about customer activity recency, not about true weekly demand.

| Branch | Weeks with data | Avg last-order events/week | Pattern |
|---|---|---|---|
| Conut | 15 weeks (Aug–Dec) | 12.1 | Stable Aug–Nov, drops in Dec |
| Conut - Tyre | 14 weeks (Sep–Dec) | 5.6 | Builds through Oct–Nov, flattens Dec |
| Conut Jnah | 18 weeks (Aug–Dec) | 14.4 | Stable Aug–Nov, **rises sharply in Dec** |
| Main Street Coffee | 8 weeks (Sep–Dec) | 2.0 | Very sparse |

**Appropriate uses of this data for forecasting:**
- "Is this branch still active in the delivery channel?"
- "Is customer recency deteriorating or improving?" (trend of `weekly_last_order_events`)
- "Is there evidence of recent delivery activity?" (last weeks with any events)

**NOT appropriate uses:**
- Do not treat as a real sub-monthly demand series.
- Do not convert to revenue via `revenue_per_delivery_order` — that chain is too assumption-heavy.
- Do not use as a primary forecasting signal.

### 2.6 Supporting: `attendance.csv` (311 shifts)

Only covers **December 2025** (weeks 49–1). Only 3 branches (no Conut main). Useful for:
- Confirming December is operationally active (not a data void)
- Staffing proxy for demand intensity (more shifts = more demand)

### 2.7 What We Do NOT Have

| Missing | Impact on forecasting |
|---|---|
| Daily sales by branch | Cannot model intra-month patterns or day-of-week effects |
| Sales by product by month | Cannot forecast at product level over time |
| Years of history | Cannot model seasonality (only 4–5 months) |
| External factors | No weather, holidays, events, promotions data |
| Table/takeaway order timestamps | Only delivery has sub-monthly temporal resolution |

### 2.8 Channel-Data Inconsistency (Must Be Acknowledged)

`dim_branch` / `avg_sales_menu` report that **Conut Jnah** and **Main Street Coffee** have no delivery channel (`has_delivery=False`). Yet `customer_orders.csv` contains delivery customer records for all 4 branches, including Jnah (18 weeks of data, avg 14.4 events/week) and MSC (8 weeks).

Possible explanations:
- **Time-window mismatch:** The channel summary may cover a different period than the customer orders file.
- **Source mismatch:** The two reports may come from different systems with different channel classification rules.
- **Channel-report coverage mismatch:** The customer orders file may capture third-party aggregator orders not tagged as "delivery" in the POS report.
- **Branch naming inconsistency:** Subtle differences in how branches are named across reports.

This inconsistency means we **cannot rely on delivery channel presence/absence from `dim_branch` alone**. For forecasting purposes, we treat `customer_orders.csv` as a weak customer-activity signal only and do not build delivery-specific sub-models from it.

---

## 3. The Core Problem

We have **4–5 data points per branch** with **high volatility** and **at least one anomalous month** (December). This is not a standard forecasting problem — it is a **tiny-sample estimation problem under extreme uncertainty**.

Any approach must:
1. Acknowledge the sample size makes formal time-series methods unreliable
2. Handle the December anomaly explicitly (not just extrapolate through it)
3. Output demand indices (not absolute financial forecasts — units are scaled)
4. Express uncertainty honestly via confidence bands
5. Be defensible to judges who will check if claims are backed by data

---

## 4. Suggested Approaches (Three Options)

### Approach A: Ensemble of Simple Estimators (Recommended)

**Philosophy:** When you have 4–5 points, no single method is reliable. Blend multiple simple methods and take the median — the ensemble is more robust than any individual.

**Step 1 — Anomaly treatment (dual-scenario approach):**
- Flag December for Conut main as `likely_partial_month` (97% drop is not plausible demand).
- Flag December spikes for Jnah and MSC as `potential_seasonal_surge`.
- For each branch affected by December anomalies, produce **two labeled scenarios**:
  - **Base case ("normal replenishment"):** Exclude anomalous month(s). Use the clean series for forecasting. This gives conservative, trend-following estimates.
  - **December-sensitive case ("surge-prepared replenishment"):** Include December with reduced weight (e.g., weight = 0.5 for surge months, weight = 0 for Conut main partial). This provides a surge-aware upper scenario.
- Both scenarios are output side-by-side. This gives operations a clear decision frame: stock for the base case, but prepare contingency capacity for the surge case.

**Step 2 — Three base estimators per branch:**

| Estimator | Method | Strength | Weakness |
|---|---|---|---|
| **Naïve** | Next month = last observed month | No overfitting | Ignores trend |
| **WMA-3** | Weighted moving average (weights: 0.5, 0.3, 0.2 on last 3 months) | Smooth | Lags behind trend changes |
| **Linear trend** | OLS regression: `month_num → revenue` | Captures direction | Assumes linearity, sensitive to outliers with n=4 |

**Step 3 — Ensemble:**
- Compute all three estimates for the primary forecast month (1 month ahead).
- Take **median** of the three as `demand_index_forecast`.
- Optionally compute months 2–3 as low-confidence scenario extensions.
- Confidence band (with capped volatility to prevent nonsensical bounds):
  - `capped_volatility` = min(volatility, 0.75)  — prevents negative lower bounds when volatility > 1.0
  - `p25` = 25th percentile of the three estimator outputs
  - `p75` = 75th percentile of the three estimator outputs
  - `relative_band_low` = max(0, p25 × (1 − capped_volatility))
  - `relative_band_high` = p75 × (1 + capped_volatility)
  - **Rule:** lower bound must never go negative.
  - The base band comes from estimator spread (p25–p75); the capped volatility factor widens it to reflect historical instability.

**Step 4 — Output columns:**

| Column | Description |
|---|---|
| `branch` | Branch name |
| `forecast_month` | Month being forecast |
| `scenario` | "base" (excl anomalies) or "december_sensitive" (incl anomalies with reduced weight) |
| `demand_index_forecast` | Ensemble median (scaled internal units) |
| `expected_change_vs_last_month` | % change from last observed month |
| `relative_band_low` | Lower uncertainty bound (always ≥ 0) |
| `relative_band_high` | Upper uncertainty bound |
| `naive_estimate` | Individual estimator output |
| `wma3_estimate` | Individual estimator output |
| `linear_estimate` | Individual estimator output |
| `method` | "ensemble_median" |
| `confidence_level` | "low" (n≤3), "medium" (n=4), "medium" (n=5) — never "high" |
| `forecast_stability_score` | 0–100 composite score (see §4.1) |
| `forecast_stability_label` | "stable" / "cautious" / "unstable" — derived from score |
| `december_flag` | Whether December anomaly affects this forecast |
| `notes` | Any branch-specific caveats |

**Pros:** Robust to any one method failing. Transparent. Defensible.
**Cons:** Still just 4–5 points. Wide bands.

### 4.1 Forecast Stability Score (Explainability Layer)

Each forecast row includes a **`forecast_stability_score`** (0–100) that synthesizes multiple quality signals into one interpretable number. This is more useful than `confidence_level` alone because it combines data quantity, data quality, and model agreement into a single column.

**Components (each scored 0–25):**

| Component | 25 (best) | 0 (worst) | Formula |
|---|---|---|---|
| **Data quantity** | n_clean ≥ 5 | n_clean ≤ 2 | `min(25, (n_clean - 2) * 25 / 3)` |
| **Volatility** | volatility ≤ 0.2 | volatility ≥ 1.5 | `max(0, 25 * (1 - volatility / 1.5))` |
| **Estimator agreement** | disagreement ≤ 10% | disagreement ≥ 100% | `max(0, 25 * (1 - disagreement))` where disagreement = (max-min)/median |
| **Anomaly absence** | No anomalies flagged | Active anomaly in last 2 months | 25 if no anomaly, 10 if anomaly flagged but handled, 0 if anomaly in forecast-adjacent month |

**Total:** Sum of four components → `forecast_stability_score` (0–100).

**Label mapping:**
- **≥ 60:** `"stable"` — reasonable for planning, bands are honest
- **30–59:** `"cautious"` — use for directional guidance, plan for wider variance
- **< 30:** `"unstable"` — treat as directional only, not actionable for firm commitments

**Example expected scores:**
- Conut main (base case): ~65 — 4 clean points, low clean-volatility, likely good agreement → `"stable"`
- Conut - Tyre: ~25 — high volatility even on clean data, estimators may disagree → `"unstable"`
- Conut Jnah (base): ~50 — 4 clean points, moderate volatility, decent agreement → `"cautious"`
- Main Street Coffee: ~20 — 3 clean points, highest volatility, similarity fallback active → `"unstable"`

This score makes the forecast output **self-documenting** — any consumer of the CSV can immediately see which forecasts to trust and which to treat as rough directional signals.

---

### Approach B: Branch Similarity Transfer (Fallback Only)

**Philosophy:** If one branch has a more interpretable pattern, transfer that pattern (scaled) to branches with noisier or shorter history.

**⚠ Important caveat:** With only 4 branches, "similarity" is more narrative than statistical. Cosine similarity on 4 data points is fragile and can produce misleading matches. This approach must be treated as a **fallback estimator**, not a regular ensemble member.

**Step 1 — Compute branch similarity:**
Using `dim_branch` (channel mix) + `feat_branch_month` (beverage share, volatility, growth trajectory):

| Pair | Shared characteristics |
|---|---|
| Conut ↔ Conut - Tyre | Both have delivery + takeaway/table. Similar beverage share (~4.5%). Both 5 months |
| Conut Jnah ↔ Main Street Coffee | Both table-only. Both have Dec surge. Similar growth trajectories |

**Step 2 — For each target branch:**
- Find the most similar branch (cosine similarity on normalized features).
- Compute the revenue ratio between target and reference (e.g., avg revenue ratio).
- Apply the reference branch's growth rate to the target branch's last value.

**Step 3 — Use as a 4th estimator in the ensemble (Approach A), under strict rules:**
- `similarity_estimate` = reference_branch_last_growth × target_branch_last_value × ratio_adjustment
- **Rule 1:** Only activate when `n_clean < 4` (i.e., the core three estimators are starved for data).
- **Rule 2:** When activated, weight it lower than the core three estimators (e.g., ensemble uses weighted median where similarity gets 0.5× the weight of the others).
- **Rule 3:** Never let it dominate the forecast — it's a stabilizer for data-poor branches, not a driver.

**Pros:** Helps branches with very little data (MSC has only 3 clean points). Uses cross-branch information.
**Cons:** Assumes branches follow similar trajectories — may not hold with 4 branches. Adds complexity.

**Recommendation:** Use **only** as a fallback estimator for data-starved branches within Approach A, not as a regular ensemble member.

---

### Approach C: Customer Activity Recency Signal (Weak Supplementary)

**Philosophy:** `customer_orders.csv` gives us weekly `last_order` event counts — a proxy for **customer activity recency**, not actual order volume. Use this as a qualitative activity signal.

**⚠ Critical clarification:** `customer_orders.csv` is a customer summary table, not an order-level event log. Grouping `last_order` by week gives "how many customers had their most recent order that week" — **not** actual weekly order volume. See §2.5 for details.

**What this can support:**
- **Branch activity check:** Is a branch still generating recent delivery customers, or is recency deteriorating?
- **Trend direction confirmation:** If the monthly_sales trend says "growing" and recency events are also increasing, that's a weak corroboration.
- **December anomaly context:** The sharp rise in Jnah recency events in Dec aligns with the revenue surge — adds qualitative confidence that December was a real demand event, not a data artifact.

**What this CANNOT support:**
- Weekly demand forecasting (it's not a demand series).
- Revenue conversion via `revenue_per_delivery_order` (too assumption-heavy across a chain of re-interpretations).
- Sub-monthly demand models of any kind.

**Additionally:** There is a channel-data inconsistency — `dim_branch` says Jnah and MSC have no delivery channel, but `customer_orders.csv` contains records for all 4 branches (see §2.8). This means the delivery activity signals from this file should be treated with extra caution.

**Recommendation:** Use only as a qualitative reasonableness check alongside the primary ensemble (Approach A). Do not convert to quantitative forecasting inputs.

---

## 5. Recommended Implementation Plan

### Phase 1: Data Preparation (`prepare.py`)

```
Input:  pipelines/output/monthly_sales.csv
        pipelines/output/feat_branch_month.csv
        pipelines/output/dim_branch.csv

Output: Cleaned time-series per branch with anomaly flags
```

**Steps:**
1. Load `monthly_sales.csv`.
2. Flag anomalies:
   - Conut Dec: `anomaly_type = "likely_partial_month"` (MoM change = -95%).
   - Conut Jnah Dec: `anomaly_type = "potential_surge"` (MoM change = +204%).
   - Main Street Coffee Dec: `anomaly_type = "potential_surge"` (MoM change = +162%).
   - Conut - Tyre Oct: `anomaly_type = "potential_spike"` (MoM change = +372%).
3. Produce two variants per branch:
   - `series_clean`: anomalous months excluded (for **base case / normal replenishment**).
   - `series_dec_weighted`: anomalous months included with reduced weight — e.g., Conut main Dec weight = 0; Jnah/MSC Dec weight = 0.5 (for **December-sensitive / surge-prepared** scenario).
4. Merge in `feat_branch_month` features (MA3, growth, volatility).
5. Merge in `dim_branch` metadata (channel flags, months_of_data).
6. Optionally load `customer_orders.csv` recency signals as qualitative branch-activity flags (see §2.5).

### Phase 2: Estimators (`estimators.py`)

Three core functions + one fallback:

```python
def naive_forecast(series, periods=1) -> list[float]:
    """Next value = last value, repeated."""

def wma_forecast(series, periods=1, weights=[0.5, 0.3, 0.2]) -> list[float]:
    """Weighted moving average of last 3 values, projected forward."""

def linear_forecast(series, periods=1) -> list[float]:
    """OLS fit on month_num → revenue, extrapolate."""

def similarity_forecast(target_branch, reference_branch, ratio, periods=1) -> list[float]:
    """Transfer growth pattern from reference branch, scaled.
    FALLBACK ONLY: activated only when n_clean < 4."""
```

Each returns a list of point estimates. `periods=1` for the primary forecast; `periods=3` only for the optional scenario extensions.

### Phase 3: Ensemble + Confidence (`ensemble.py`)

```python
def ensemble_forecast(branch, series_clean, series_dec_weighted, periods=1) -> pd.DataFrame:
    """
    For EACH scenario (base + december_sensitive):
      1. Run core estimators (naive, WMA-3, linear). If n_clean < 4, also run similarity (fallback).
      2. Take median as point estimate (weighted median if similarity is active, with similarity at 0.5× weight).
      3. Compute confidence band using capped volatility and estimator spread (see §4 Step 3).
      4. Compute forecast_stability_score (see §4.1).
      5. Optionally extend to months 2–3 as low-confidence scenario extensions.
      6. Return forecast DataFrame with both scenarios side-by-side.
    """
```

**Confidence level logic:**
- `n_clean >= 5` and `volatility < 0.5`: "medium"
- `n_clean >= 4` and `volatility < 1.0`: "low-medium"
- `n_clean < 4` or `volatility >= 1.0`: "low"
- Never "high" — we don't have enough data for that.

### Phase 4: Output + Artifacts (`run_forecast.py`)

```
Output: pipelines/demand_forecast/output/
        ├── demand_forecast_all.csv        # All branches, all periods
        ├── demand_forecast_by_branch/     # One CSV per branch
        │   ├── conut.csv
        │   ├── conut_tyre.csv
        │   ├── conut_jnah.csv
        │   └── main_street_coffee.csv
        └── forecast_metadata.json         # Run timestamp, parameters, anomaly flags
```

**Output schema for `demand_forecast_all.csv`:**

| Column | Type | Description |
|---|---|---|
| `branch` | str | Branch name |
| `forecast_period` | int | 1 (primary), 2 or 3 (optional low-confidence extensions) |
| `is_primary` | bool | True for period=1 (credible planning signal), False for 2–3 (directional only) |
| `forecast_month` | str | "January 2026", "February 2026", etc. |
| `demand_index_forecast` | float | Ensemble median (scaled units) |
| `expected_change_vs_last_clean_month` | float | % change vs last non-anomalous month |
| `relative_band_low` | float | Lower bound |
| `relative_band_high` | float | Upper bound |
| `band_width_pct` | float | (high - low) / forecast — measure of uncertainty |
| `naive_estimate` | float | Individual estimator |
| `wma3_estimate` | float | Individual estimator |
| `linear_estimate` | float | Individual estimator |
| `similarity_estimate` | float | Fallback estimator (only populated when n_clean < 4, see §4 Approach B) |
| `method` | str | "ensemble_median" |
| `confidence_level` | str | "low" / "low-medium" / "medium" |
| `n_months_used` | int | How many months in the clean series |
| `last_clean_month` | str | Last non-anomalous month used |
| `december_anomaly_flag` | str | "likely_partial_month" / "potential_surge" / "none" |
| `notes` | str | Branch-specific caveats |

---

## 6. Branch-by-Branch Forecast Strategy

Each branch produces **two labeled scenarios** for the primary forecast month (January 2026). Operations can choose which to plan around:

- **Base case ("normal replenishment"):** Conservative, trend-following. Excludes anomalous months.
- **December-sensitive ("surge-prepared replenishment"):** Includes December with appropriate weighting. Acknowledges the possibility that December-like demand may recur.

### Conut (main)

- **Problem:** Dec is 5% of Nov → almost certainly a partial month.
- **Base case:** Exclude Dec. Use Aug–Nov (4 points). Growing trend: +42%, +45%, +19%.
  - Expected: Continued growth but decelerating. Linear trend → ~1.5–1.6B for Jan. Naïve → 1.35B.
- **December-sensitive case:** Dec gets weight = 0 (it's a partial-month distortion, not a demand signal). So this scenario is identical to base for Conut main.
- **Stability:** Likely "stable" or "cautious" (4 clean points, moderate clean volatility ~0.14, low estimator disagreement on clean data).
- **Missing:** No attendance data for Conut main → cannot cross-validate with staffing.

### Conut - Tyre

- **Problem:** Oct spike (+372%) is hard to explain. Pattern: 477M → 445M → **2.1B** → 1.1B → 1.0B.
- **Base case:** Exclude Oct. Use 4 points: 477M, 445M, 1.1B, 1.0B. Still volatile but more coherent.
  - Expected: Stabilizing around 1.0–1.1B range.
- **December-sensitive case:** Include Oct (with reduced weight 0.5) and keep Dec as-is (no December anomaly for Tyre).
  - Expected: Higher and wider — Oct pulls the trend upward.
- **Stability:** Likely "unstable" (high volatility 1.97 even on clean, estimators may disagree significantly).

### Conut Jnah

- **Problem:** Dec surges to 3× Nov (2.88B vs 948M). Is this seasonal or anomalous?
- **Base case:** Exclude Dec. Use 4 points: Aug–Nov, steady growth (+96%, +10%, +21%).
  - Expected: ~1.0–1.2B for Jan. Moderate confidence on trend direction.
- **December-sensitive case:** Include Dec with weight = 0.5.
  - Expected: Significantly higher — ~2.0–3.0B. Represents a "prepare for another December-like surge" scenario.
  - Operationally: this is the "order extra perishable stock" signal.
- **Stability:** "cautious" (base) / "unstable" (December-sensitive).

### Main Street Coffee

- **Problem:** Only 4 months. Sep is tiny (146M) — likely a ramp-up month. Dec surges similarly to Jnah.
- **Base case:** Exclude Dec. 3 clean points only: Sep → Oct → Nov: 146M → 921M → 1.17B. Rapid deceleration.
  - Expected: ~1.2–1.5B, but highly uncertain with only 3 points.
  - **Activates similarity fallback** from Conut Jnah (similar profile: table-only, Dec surge, similar beverage share) since n_clean < 4.
- **December-sensitive case:** Include Dec with weight = 0.5.
  - Expected: Very steep trend → ~2.5–3.5B. Enormous band width.
- **Stability:** "unstable" for both scenarios (3–4 clean points, highest volatility in fleet: 2.61).
- **Note:** `is_partial_history=True` — fewer months than other branches.

---

## 7. How This Supports Inventory & Supply Chain

The brief says "forecast demand per branch to support inventory and supply chain decisions." With our data, we can provide:

| Decision | What we output | How it helps |
|---|---|---|
| **How much to stock next month** | `demand_index_forecast` (base scenario) + `forecast_stability_label` | Base case gives the conservative target. Stability label tells ops how much to trust it |
| **Surge preparedness** | `demand_index_forecast` (december_sensitive scenario) | If the December surge recurs, this is the upper planning bound |
| **Which branches need more** | Rank by `expected_change_vs_last_clean_month` | Rising branches get priority |
| **Uncertainty-aware planning** | `relative_band_low` / `relative_band_high` | Use low estimate for perishable stock, high for non-perishable |
| **Forecast trustworthiness** | `forecast_stability_score` + `forecast_stability_label` | Quick triage: stable forecasts → commit, cautious → flexible plan, unstable → directional only |
| **Seasonal awareness** | `december_anomaly_flag` + dual scenarios | Dec may be fundamentally different — both scenarios are visible side-by-side |
| **Cross-branch comparison** | All branches in one table | Operations can allocate resources across the fleet |

**What we CANNOT do** (and should say clearly):
- Daily or weekly demand forecasts (no daily sales data for total revenue).
- Product-level demand forecasts (items data has no time axis).
- Seasonal decomposition (only 4–5 months, no year-over-year).
- Predict absolute revenue (units are scaled).

---

## 8. File Structure

```
pipelines/demand_forecast/
├── PLAN.md                  # This document
├── prepare.py               # Data loading, anomaly flagging, series prep
├── estimators.py            # Naïve, WMA-3, Linear, Similarity estimators
├── ensemble.py              # Combine estimators, compute bands + confidence
├── run_forecast.py          # Orchestrator: prepare → estimate → ensemble → save
└── output/                  # Generated outputs
    ├── demand_forecast_all.csv
    ├── demand_forecast_by_branch/
    │   ├── conut.csv
    │   ├── conut_tyre.csv
    │   ├── conut_jnah.csv
    │   └── main_street_coffee.csv
    └── forecast_metadata.json
```

---

## 9. Parameters / Configuration

| Parameter | Default | Rationale |
|---|---|---|
| `PRIMARY_PERIODS` | 1 | Primary forecast: 1 month ahead (January 2026) — the credible planning signal |
| `EXTENSION_PERIODS` | 2 | Optional scenario extension: months 2–3 (Feb–Mar 2026) — low-confidence directional only |
| `WMA_WEIGHTS` | [0.5, 0.3, 0.2] | Recency-weighted, standard for small samples |
| `ANOMALY_MOM_THRESHOLD` | 2.0 | Flag if MoM growth > 200% or < -80% |
| `MIN_MONTHS_FOR_LINEAR` | 3 | Need at least 3 points for OLS |
| `CAPPED_VOLATILITY_MAX` | 0.75 | Cap volatility for band construction — prevents negative lower bounds |
| `DEC_SURGE_WEIGHT` | 0.5 | Weight for December surge months in the December-sensitive scenario |
| `DEC_PARTIAL_WEIGHT` | 0.0 | Weight for Conut main Dec (partial month — effectively excluded in both scenarios) |
| `SIMILARITY_ACTIVATION_THRESHOLD` | 4 | Only activate similarity estimator when `n_clean < 4` |
| `SIMILARITY_WEIGHT_FACTOR` | 0.5 | Similarity estimator gets half the weight of core estimators in weighted median |
| `SIMILARITY_TOP_K` | 1 | Use the single most-similar branch for transfer |

---

## 10. Validation Strategy

Since we have no held-out test set (all data is needed for fitting), validation must be:

1. **Leave-one-out backtesting**: For each branch, hold out the last clean month, forecast it from the remaining, measure error. Repeat for second-to-last if possible. This is the most honest test with small data.
2. **Estimator disagreement score**: Compute `(max_estimate - min_estimate) / median_estimate` across the three core estimators. If > 1.0 (100% spread), flag as "unstable." This feeds into `forecast_stability_score`.
3. **Historical range sanity check**: Verify the forecast falls within [0.5×, 2.0×] of the historical min–max range (excluding flagged anomalies). Forecasts outside this range get a warning in `notes`.
4. **Branch share ranking stability**: Check whether the forecasted branch ranking (by demand) is consistent with historical rankings. A forecast that reverses the established hierarchy should be flagged.
5. **Visual inspection**: Plot actual + forecast + bands for each branch. A human should review.

**Removed:** Previously included a reconciliation check against `avg_sales_menu` totals. That validation was invalid because `avg_sales_menu` is a branch-channel aggregate without a time dimension — it is not a next-month benchmark and cannot validate monthly forecasts.

---

## 11. Known Limitations (Must Be Stated in Output)

1. **4–5 data points.** This is not enough for any statistically reliable forecast. Our output is a "best structured estimate," not a prediction.
2. **December is anomalous for all branches** in different directions. This may be seasonal, data artifact, or both. The dual-scenario approach handles this but does not resolve the underlying ambiguity.
3. **All values are in scaled/arbitrary units.** The demand index is relative — do not interpret as currency.
4. **No product-level time series.** We cannot forecast which products will be in demand.
5. **No daily granularity.** Intra-month planning is not possible from this data.
6. **Main Street Coffee has only 4 months** (3 clean). Any forecast for this branch is highly speculative.
7. **Customer activity proxy** (Approach C) is based on `last_order` timestamps in a customer summary table, not actual order events. It is a qualitative recency signal, not a demand series.
8. **Channel-data inconsistency:** `dim_branch` says Jnah and MSC have no delivery, but `customer_orders.csv` contains records for all 4 branches (see §2.8). This limits confidence in delivery-channel assertions.
9. **Months 2–3 forecasts are low-confidence scenario extensions.** Only the 1-month-ahead primary forecast should be used for operational planning commitments.
10. **Branch similarity** (Approach B) is a fallback for data-starved branches, not a validated cross-branch model. With only 4 branches, similarity is more narrative than statistical.
