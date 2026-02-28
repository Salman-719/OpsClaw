# Demand Forecast by Branch

Forecasts monthly demand per branch with dual scenarios, confidence bands, and a self-documenting stability score.

## Quick Start

```bash
cd /path/to/Hackathon
source .venv/bin/activate
python -m pipelines.demand_forecast.run_forecast
```

## Requirements

- Python 3.10+
- pandas, numpy (installed in `.venv`)
- Pipeline output files in `pipelines/output/`:
  - `monthly_sales.csv`
  - `feat_branch_month.csv`
  - `dim_branch.csv`

## What It Produces

```
pipelines/demand_forecast/output/
├── demand_forecast_all.csv              # 24 rows — all branches × scenarios × periods
├── demand_forecast_by_branch/
│   ├── conut.csv
│   ├── conut_tyre.csv
│   ├── conut_jnah.csv
│   └── main_street_coffee.csv
└── forecast_metadata.json               # Parameters, timestamps, anomaly flags
```

**24 rows = 4 branches × 2 scenarios × 3 periods**

## How to Read the Output

| Column | What to look at |
|---|---|
| `scenario` | `base` = normal planning. `december_sensitive` = surge-prepared. |
| `is_primary` | `True` = January 2026, credible. `False` = Feb/Mar, directional only. |
| `demand_index_forecast` | The point estimate (scaled units, not currency). |
| `relative_band_low / high` | Planning range. Use low for perishables, high for safety stock. |
| `forecast_stability_label` | **stable** → commit. **cautious** → flex plan. **unstable** → directional only. |
| `forecast_stability_score` | 0–100 composite. Higher = more trustworthy. |
| `notes` | Warnings and caveats in plain text. |

## Module Structure

| File | Role |
|---|---|
| `prepare.py` | Load CSVs, flag anomalies, build clean + weighted series per branch |
| `estimators.py` | 4 estimators: naïve, WMA-3, linear OLS, similarity fallback |
| `ensemble.py` | Combine estimators → median, capped-volatility bands, stability score |
| `run_forecast.py` | Orchestrator: prepare → ensemble → save |
| `PLAN.md` | Full design rationale and data analysis |
| `METHODOLOGY.md` | Detailed technical explanation |
