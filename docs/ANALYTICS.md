# Analytics Features

> Five analytics modules that transform processed data into actionable business intelligence for the Conut bakery chain.

---

## Overview

Each analytics feature:
1. Reads processed CSVs from the ETL pipeline output
2. Performs statistical analysis / machine learning
3. Writes results to DynamoDB for the AI agent to query
4. Uploads result CSVs to S3 for archival

All 5 features run **in parallel** via AWS Step Functions after the ETL completes.

---

## Feature 1: Combo Optimization (`analytics/combo/`)

### Purpose
Identifies which products are frequently bought together using **association rule mining** (market basket analysis). Enables bundling strategies and menu optimization.

### Key Files

| File | Description |
|------|-------------|
| `combo_optimization.py` | Core association rule mining (Apriori-style) |
| `combo_queries.py` | Query interface for combo data |
| `data/` | Intermediate data storage |

### Methodology
- Builds transaction baskets from `transaction_baskets_basket_core.csv`
- Computes **support**, **confidence**, and **lift** for item pairs
- Scopes: overall, per-branch, per-channel

### Key Metrics

| Metric | Description | Interpretation |
|--------|-------------|----------------|
| **Support** | Frequency of pair appearing together | Higher = more common |
| **Confidence** | P(B | A) — probability of B given A | Higher = stronger prediction |
| **Lift** | Confidence / P(B) — association strength | >3 = strong, >5 = very strong |

### DynamoDB Schema

| Table | PK | SK | Data |
|-------|----|----|------|
| `conut-ops-combo-dev` | Scope (e.g., `overall`, `branch:Conut Jnah`) | `item_a#item_b` | support, confidence, lift |

### Example Query
> "Which product combos have lift greater than 5?"
> "What are the top combos for Conut Jnah?"

---

## Feature 2: Demand Forecast (`analytics/forecast/`)

### Purpose
Predicts future order volumes per branch at 1, 2, and 3-month horizons using ensemble time-series methods.

### Key Files

| File | Description |
|------|-------------|
| `run_forecast.py` | Main forecast runner |
| `prepare.py` | Data preparation and cleaning |
| `estimators.py` | Individual forecasting models |
| `ensemble.py` | Ensemble model combining estimators |
| `METHODOLOGY.md` | Detailed methodology documentation |

### Methodology
- **Data preparation:** Cleans and aggregates monthly sales data
- **Estimators:** Multiple time-series models (trend, seasonal, averaging)
- **Ensemble:** Weighted combination for robustness
- **Scenarios:** `base` (conservative) and `optimistic` (growth-adjusted)
- **Horizons:** 1-month (most reliable), 2-month, 3-month ahead

### DynamoDB Schema

| Table | PK | SK | Data |
|-------|----|----|------|
| `conut-ops-forecast-dev` | `branch#scenario` (e.g., `Conut#base`) | `period#1` | predicted_orders, confidence, upper/lower bounds |

### Example Queries
> "What's the demand forecast for Conut Jnah?"
> "Compare forecasts across all branches"
> "Show optimistic vs base scenario for Tyre"

---

## Feature 3: Expansion Feasibility (`analytics/expansion/`)

### Purpose
Evaluates whether candidate branches (batroun, bliss, jnah, tyre) are feasible for expansion, based on operational KPIs and a composite feasibility score.

### Key Files

| File | Description |
|------|-------------|
| `run.py` | Main expansion analysis runner |
| `kpis.py` | KPI calculation (revenue, orders, avg ticket, etc.) |
| `scoring.py` | Feasibility score computation (0–1 scale) |
| `recommend.py` | Generates expansion recommendation |
| `cleaning.py` | Data cleaning utilities |
| `utils.py` | Helper functions |
| `api.py` | Query interface |
| `agent_interface.py` | Agent-facing API |

### Methodology
- **KPIs per branch:** Revenue, order count, average ticket size, growth rate, consistency
- **Feasibility score:** Weighted composite of normalized KPIs (0–1 scale)
- **Tiers:** High (>0.6), Medium (0.4–0.6), Low (<0.4)
- **Recommendation:** Identifies the top candidate with reasoning

### DynamoDB Schema

| Table | PK | SK | Data |
|-------|----|----|------|
| `conut-ops-expansion-dev` | Branch (e.g., `batroun`) | `kpi` | Revenue, orders, avg_ticket, etc. |
|  | Branch | `feasibility` | Score, tier |
|  | `recommendation` | `expansion` | Top candidate, reasoning |

### Example Queries
> "Should we expand to Batroun?"
> "Rank all candidate branches by feasibility"
> "What are the KPIs for Tyre?"

---

## Feature 4: Shift Staffing Estimation (`analytics/staffing/`)

### Purpose
Analyzes hourly demand patterns vs. current staffing levels to identify understaffed and overstaffed time slots.

### Key Files

| File | Description |
|------|-------------|
| `analyze.py` | Staffing gap analysis engine |
| `demand.py` | Demand curve estimation |
| `supply.py` | Staff supply modeling |
| `model.py` | Gap calculation model |
| `config.py` | Staffing parameters |
| `loaders.py` | Data loading utilities |
| `visualize.py` | Chart/visualization generation |

### Methodology
- **Demand side:** Hourly transaction counts by branch and day of week
- **Supply side:** Current shift schedules from attendance data
- **Gap = Demand − Supply:**
  - Gap > 0 → Understaffed (need more staff)
  - Gap < 0 → Overstaffed (excess staff)
- **Findings:** Branch-level summary with peak hours, worst days

### DynamoDB Schema

| Table | PK | SK | Data |
|-------|----|----|------|
| `conut-ops-staffing-dev` | Branch (e.g., `Conut Jnah`) | `findings` | Peak hours, avg gap, recommendation |
|  | Branch | `gap#Monday#09` | demand, supply, gap, is_understaffed |

### Example Queries
> "Show me staffing gaps for Main Street Coffee on Saturday"
> "Which time slots are most understaffed?"
> "Give me a staffing summary for all branches"

---

## Feature 5: Growth Strategy (`analytics/growth/`)

### Purpose
Identifies growth opportunities in the beverage category (coffee & milkshakes) through attachment rate analysis and food→beverage association rules.

### Key Files

| File | Description |
|------|-------------|
| `run.py` | Main growth analysis runner |
| `kpis.py` | Beverage KPI calculation |
| `scoring.py` | Growth potential scoring |
| `basket_analysis.py` | Food→beverage association analysis |
| `beverage_detection.py` | Beverage item classification |
| `loader.py` | Data loading utilities |
| `parsing.py` | Data parsing helpers |
| `utils.py` | Helper functions |
| `agent_interface.py` | Agent-facing API |

### Methodology
- **Beverage detection:** Classifies items as coffee, milkshake, or non-beverage
- **Attachment rate:** % of transactions containing at least one beverage
- **Growth potential:** Score based on current attachment rate vs. benchmark
- **Association rules:** Food items that most frequently pair with beverages (lift-based)
- **Strategy:** Recommends targeted upselling for low-attachment-rate branches

### DynamoDB Schema

| Table | PK | SK | Data |
|-------|----|----|------|
| `conut-ops-growth-dev` | Branch (e.g., `Conut Jnah`) | `beverage_kpi` | Attachment rate, beverage share, count |
|  | Branch | `growth_potential` | Score, rank, benchmark gap |
|  | Branch | `rule#<food_item>` | Lift, confidence, support |
|  | `recommendation` | `growth` | Overall strategy |

### Example Queries
> "What's the beverage growth potential for each branch?"
> "Which food items drive the most beverage sales?"
> "Give me the overall growth strategy recommendation"

---

## Lambda Handlers

Each analytics feature has a corresponding Lambda handler in `infra/handlers/`:

| Handler | Feature | Input |
|---------|---------|-------|
| `forecast_handler.py` | Demand Forecast | Processed CSVs from S3 |
| `combo_handler.py` | Combo Optimization | Processed CSVs from S3 |
| `expansion_handler.py` | Expansion Feasibility | Processed CSVs from S3 |
| `staffing_handler.py` | Shift Staffing | Processed CSVs from S3 |
| `growth_handler.py` | Growth Strategy | Processed CSVs from S3 |

### Lambda Flow

1. Download processed CSVs from `s3://<bucket>/processed/`
2. Run the analytics module
3. Write results to DynamoDB
4. Upload result CSVs to `s3://<bucket>/results/<feature>/`
5. Return summary for Step Functions

---

## Step Functions Pipeline

All 5 analytics run **in parallel** after the ETL stage:

```
Start
  │
  ▼
┌─────┐
│ ETL │ → Downloads CSVs from S3, parses, uploads processed data
└──┬──┘
   │
   ▼
┌──────────────────────────────────────┐
│         Parallel Analytics           │
│  ┌──────────┐  ┌──────────┐         │
│  │ Forecast │  │  Combo   │         │
│  └──────────┘  └──────────┘         │
│  ┌──────────┐  ┌──────────┐  ┌─────┐│
│  │Expansion │  │ Staffing │  │Growth││
│  └──────────┘  └──────────┘  └─────┘│
└──────────────────────────────────────┘
   │
   ▼
  End
```
