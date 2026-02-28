# DynamoDB Schema Reference

> **OpsClaw — Conut AI Operations Agent**
>
> This document describes every DynamoDB table, its key design, stored attributes,
> and example queries for the AI agent or any downstream consumer.

---

## Overview

| # | Feature | Table Name | pk | sk | Row Count |
|---|---------|------------|----|----|-----------|
| 1 | Demand Forecast | `conut-ops-forecast-dev` | `{branch}#{scenario}` | `period#{N}` | 24 |
| 2 | Combo Optimization | `conut-ops-combo-dev` | `{scope}` | `{item_a}#{item_b}` | variable |
| 3 | Expansion Feasibility | `conut-ops-expansion-dev` | `{branch}` or `"recommendation"` | `"kpi"` / `"feasibility"` / `"expansion"` | ~9 |
| 4 | Staffing Estimation | `conut-ops-staffing-dev` | `{branch}` | `"findings"` / `"gap#{day}#{HH}"` | ~57 |
| 5 | Growth Strategy | `conut-ops-growth-dev` | `{branch}` or `"recommendation"` | `"beverage_kpi"` / `"growth_potential"` / `"rule#…"` / `"growth"` | ~41 |

Every item includes an **`explanation`** column — a human-readable sentence the
agent can return directly to the user without further processing.

---

## 1. Demand Forecast

**Table:** `conut-ops-forecast-dev`

### Key Design

| Key | Pattern | Example |
|-----|---------|---------|
| `pk` | `{branch}#{scenario}` | `Conut#base`, `Conut Jnah#optimistic` |
| `sk` | `period#{N}` | `period#1`, `period#2`, `period#3` |

- **Branches:** Conut, Conut - Tyre, Conut Jnah, Main Street Coffee
- **Scenarios:** `base`, `optimistic`
- **Periods:** 1 (1-month ahead), 2 (2-month), 3 (3-month)

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `branch` | S | Branch name |
| `scenario` | S | `base` or `optimistic` |
| `forecast_period` | N | 1, 2, or 3 |
| `is_primary` | S | `"True"` if period=1 (most reliable) |
| `forecast_month` | S | e.g. `"January 2026"` |
| `demand_index_forecast` | N | Forecasted demand in LBP |
| `expected_change_vs_last_clean_month` | N | % change vs last clean month |
| `relative_band_low` | N | Lower confidence bound |
| `relative_band_high` | N | Upper confidence bound |
| `band_width_pct` | N | Band width as fraction of forecast |
| `naive_estimate` | N | Naive estimator value |
| `wma3_estimate` | N | Weighted moving average (3-month) |
| `linear_estimate` | N | Linear OLS trend extrapolation |
| `similarity_estimate` | N | Similarity-based estimate (if available) |
| `method` | S | `"ensemble_median"` |
| `confidence_level` | S | `"low-medium"`, `"medium"`, etc. |
| `forecast_stability_score` | N | 0–100 composite stability |
| `forecast_stability_label` | S | `"stable"`, `"moderate"`, `"unstable"` |
| `n_months_used` | N | Clean months in training window |
| `last_clean_month` | S | Last non-anomalous month |
| `december_anomaly_flag` | S | `"likely_partial_month"` or empty |
| `explanation` | S | Full human-readable paragraph |

### Access Patterns

```python
# Get all forecasts for a branch
table.query(KeyConditionExpression=Key("pk").eq("Conut#base"))

# Get the primary 1-month forecast for a branch
table.get_item(Key={"pk": "Conut#base", "sk": "period#1"})

# Get all base-scenario forecasts (scan with filter)
table.scan(FilterExpression=Attr("scenario").eq("base") & Attr("is_primary").eq("True"))

# Compare branches on primary forecast
# Query each pk: "Conut#base", "Conut Jnah#base", "Conut - Tyre#base", "Main Street Coffee#base"
# with sk = "period#1"
```

---

## 2. Combo Optimization

**Table:** `conut-ops-combo-dev`

### Key Design

| Key | Pattern | Example |
|-----|---------|---------|
| `pk` | `{scope}` | `overall`, `branch:Conut Jnah`, `branch:Conut - Tyre\|channel:delivery` |
| `sk` | `{item_a}#{item_b}` | `mocha frappe#conut the one` |

Scopes are hierarchical:
- `overall` — all branches, all channels
- `branch:{name}` — single branch, all channels
- `channel:{type}` — all branches, single channel
- `branch:{name}|channel:{type}` — single branch + channel

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `scope` | S | Scope identifier (same as pk) |
| `item_a` | S | First item in the pair |
| `item_b` | S | Second item in the pair |
| `n_orders` | N | Total orders in this scope |
| `count_a` | N | Orders containing item_a |
| `count_b` | N | Orders containing item_b |
| `count_ab` | N | Orders containing both items |
| `support` | N | Fraction of orders with both items |
| `confidence_ab` | N | P(item_b | item_a) |
| `confidence_ba` | N | P(item_a | item_b) |
| `lift` | N | Association strength (>1 = positive) |
| `explanation` | S | Human-readable association summary |

### Access Patterns

```python
# Get all combo pairs across all branches
table.query(KeyConditionExpression=Key("pk").eq("overall"))

# Get all pairs for a specific branch
table.query(KeyConditionExpression=Key("pk").eq("branch:Conut Jnah"))

# Get a specific pair
table.get_item(Key={"pk": "overall", "sk": "mocha frappe#conut the one"})

# Get strongest combos (scan + filter by lift)
table.scan(FilterExpression=Attr("lift").gte(Decimal("3.0")))

# Get branch+channel pairs
table.query(KeyConditionExpression=Key("pk").eq("branch:Conut - Tyre|channel:delivery"))
```

### Lift Interpretation

| Lift | Meaning |
|------|---------|
| ≥ 5.0 | Very strong — always promote together |
| 2.0 – 5.0 | Strong — good combo candidate |
| 1.2 – 2.0 | Moderate — worth testing |
| 1.0 – 1.2 | Weak — marginal association |
| < 1.0 | Negative — bought less together than expected |

---

## 3. Expansion Feasibility

**Table:** `conut-ops-expansion-dev`

### Key Design

| Key | Pattern | Description |
|-----|---------|-------------|
| `pk` | `{branch}` | Branch name (e.g. `batroun`, `jnah`, `tyre`, `bliss`) |
| `sk` | `"kpi"` | Branch operational KPIs |
| `sk` | `"feasibility"` | Normalized feasibility score |
| `pk` | `"recommendation"` | Fixed key for the final recommendation |
| `sk` | `"expansion"` | The expansion recommendation record |

### Record: Branch KPIs (`sk = "kpi"`)

| Attribute | Type | Description |
|-----------|------|-------------|
| `record_type` | S | `"branch_kpi"` |
| `branch` | S | Branch name |
| `avg_monthly_revenue` | N | Average monthly revenue (LBP) |
| `recent_growth_rate` | N | Recent growth trend |
| `revenue_volatility` | N | Revenue stability (0=stable, 1=volatile) |
| `pct_change_first_last` | N | % change over full history |
| `n_months` | N | Months of data available |
| `is_partial_history` | S | `"True"` if < 12 months |
| `delivery_revenue` | N | Delivery channel revenue |
| `delivery_share` | N | Delivery as % of total |
| `total_hours` | N | Total staff hours |
| `revenue_per_hour` | N | Revenue efficiency metric |
| `total_tax` | N | Total tax paid |
| `tax_burden` | N | Tax as % of revenue |
| `explanation` | S | Human-readable KPI summary |

### Record: Feasibility Score (`sk = "feasibility"`)

| Attribute | Type | Description |
|-----------|------|-------------|
| `record_type` | S | `"feasibility_score"` |
| `branch` | S | Branch name |
| `feasibility_score` | N | 0–1 composite score |
| `score_tier` | S | `"High"`, `"Medium"`, or `"Low"` |
| `top_drivers` | S | e.g. `"growth, revenue"` |
| `norm_growth` | N | Normalized growth component |
| `norm_revenue` | N | Normalized revenue component |
| `norm_volatility` | N | Normalized volatility component |
| `norm_delivery` | N | Normalized delivery component |
| `norm_ops_eff` | N | Normalized ops efficiency component |
| `stability` | N | Stability sub-score |
| `explanation` | S | Human-readable feasibility outlook |

### Record: Recommendation (`pk = "recommendation"`, `sk = "expansion"`)

| Attribute | Type | Description |
|-----------|------|-------------|
| `record_type` | S | `"recommendation"` |
| `recommended_region` | S | e.g. `"North Lebanon"` |
| `candidate_locations` | S | Comma-separated list: `"Batroun region, Byblos, Tripoli"` |
| `best_branch_to_replicate` | S | Branch profile to copy |
| `feasibility_tier` | S | `"High"`, `"Medium"`, or `"Low"` |
| `overall_feasibility` | N | Best region's score |
| `region_scores` | S | JSON string: `{"beirut": 0.43, "north": 0.64, "south": 0.55}` |
| `growth_summary` | S | JSON string with per-branch growth details |
| `explanation` | S | Human-readable recommendation |

### Access Patterns

```python
# Get all data for a branch (KPI + feasibility in one query)
table.query(KeyConditionExpression=Key("pk").eq("jnah"))

# Get just the KPI for a branch
table.get_item(Key={"pk": "batroun", "sk": "kpi"})

# Get just the feasibility score
table.get_item(Key={"pk": "jnah", "sk": "feasibility"})

# Get the expansion recommendation
table.get_item(Key={"pk": "recommendation", "sk": "expansion"})

# Find all High-tier branches
table.scan(FilterExpression=Attr("score_tier").eq("High"))
```

---

## 4. Staffing Estimation

**Table:** `conut-ops-staffing-dev`

### Key Design

| Key | Pattern | Example |
|-----|---------|---------|
| `pk` | `{branch}` | `Conut - Tyre`, `Conut Jnah`, `Main Street Coffee` |
| `sk` | `"findings"` | Branch-level summary |
| `sk` | `"gap#{day}#{HH}"` | `gap#Friday#23`, `gap#Monday#21` |

> **Note:** Only understaffed and overstaffed slots are stored. Balanced slots
> are excluded to keep the table lean and agent queries focused on actionable gaps.

### Record: Branch Findings (`sk = "findings"`)

| Attribute | Type | Description |
|-----------|------|-------------|
| `record_type` | S | `"staffing_findings"` |
| `branch` | S | Branch name |
| `demand_confidence` | S | `"high"`, `"low"` |
| `share_source` | S | Method used for delivery share |
| `analysis_slots` | N | Total day×hour slots analyzed |
| `understaffed_slots` | N | Count of understaffed slots |
| `balanced_slots` | N | Count of balanced slots |
| `overstaffed_slots` | N | Count of overstaffed slots |
| `avg_active_employees_across_slots` | N | Avg employees currently working |
| `avg_required_employees_base` | N | Avg employees needed |
| `worst_understaffed_slot` | S | e.g. `"Friday 23:00"` |
| `worst_understaffed_gap` | N | Biggest understaffing gap |
| `worst_overstaffed_slot` | S | e.g. `"Sunday 15:00"` |
| `worst_overstaffed_gap` | N | Biggest overstaffing gap (negative) |
| `top_understaffed_slots` | S | Semicolon-separated list with gaps |
| `top_overstaffed_slots` | S | Semicolon-separated list with gaps |
| `recommendation` | S | Actionable staffing advice |
| `explanation` | S | Human-readable staffing overview |

### Record: Hourly Gap (`sk = "gap#{day}#{HH}"`)

| Attribute | Type | Description |
|-----------|------|-------------|
| `record_type` | S | `"staffing_gap"` |
| `branch` | S | Branch name |
| `day_of_week` | S | `"Monday"` … `"Sunday"` |
| `hour` | N | 0–23 |
| `avg_active_employees` | N | Employees currently scheduled |
| `required_employees_base` | N | Employees needed (base demand) |
| `gap_base` | N | Positive = understaffed, negative = overstaffed |
| `status` | S | `"understaffed"` or `"overstaffed"` |
| `delivery_orders_est` | N | Estimated delivery orders for this slot |
| `total_orders_est_base` | N | Estimated total orders for this slot |
| `explanation` | S | Human-readable action for this slot |

### Access Patterns

```python
# Get full staffing picture for a branch (findings + all gaps)
table.query(KeyConditionExpression=Key("pk").eq("Conut Jnah"))

# Get just the branch-level summary
table.get_item(Key={"pk": "Conut - Tyre", "sk": "findings"})

# Get gap for a specific slot
table.get_item(Key={"pk": "Conut Jnah", "sk": "gap#Monday#21"})

# Get all Friday gaps for a branch
table.query(
    KeyConditionExpression=Key("pk").eq("Conut Jnah") & Key("sk").begins_with("gap#Friday")
)

# Get all understaffed slots across all branches
table.scan(FilterExpression=Attr("status").eq("understaffed"))

# Get worst gaps (scan + filter by gap magnitude)
table.scan(FilterExpression=Attr("gap_base").gte(Decimal("3.0")))
```

---

## 5. Growth Strategy (Coffee & Milkshake)

**Table:** `conut-ops-growth-dev`

### Key Design

| Key | Pattern | Example |
|-----|---------|---------|
| `pk` | `{branch}` | `Conut Jnah`, `Conut - Tyre`, `Main Street Coffee` |
| `sk` | `"beverage_kpi"` | Beverage attachment KPIs |
| `sk` | `"growth_potential"` | Growth ranking + score |
| `sk` | `"rule#{antecedent}#{consequent}"` | `rule#conut the one#mocha frappe` |
| `pk` | `"recommendation"` | Fixed key for strategy recommendation |
| `sk` | `"growth"` | The growth recommendation record |

### Record: Beverage KPI (`sk = "beverage_kpi"`)

| Attribute | Type | Description |
|-----------|------|-------------|
| `record_type` | S | `"beverage_kpi"` |
| `branch` | S | Branch name |
| `total_orders` | N | Total basket orders |
| `beverage_orders` | N | Orders that include a beverage |
| `beverage_attachment_rate` | N | beverage_orders / total_orders |
| `best_branch_rate` | N | Best branch's attachment rate (benchmark) |
| `beverage_gap_to_best` | N | Gap to benchmark (0 = you are the best) |
| `total_amount` | N | Total revenue |
| `bev_amount` | N | Beverage revenue |
| `bev_revenue_share` | N | Beverage % of total revenue |
| `explanation` | S | Human-readable benchmark comparison |

### Record: Growth Potential (`sk = "growth_potential"`)

| Attribute | Type | Description |
|-----------|------|-------------|
| `record_type` | S | `"growth_potential"` |
| `branch` | S | Branch name |
| `potential_score` | N | 0–1 composite (higher = more opportunity) |
| `potential_rank` | N | 1 = highest potential |
| `beverage_attachment_rate` | N | Current rate |
| `beverage_gap_to_best` | N | Gap to benchmark |
| `low_attachment_score` | N | Score component: low attachment |
| `order_volume_score` | N | Score component: order volume |
| `avg_lift` | N | Average lift from association rules |
| `assoc_lift_score` | N | Score component: association strength |
| `top_bundle_rule` | S | e.g. `"hot chocolate combo → oreo milkshake (lift=98.00)"` |
| `explanation` | S | Human-readable ranking with priority and recommendation |

### Record: Association Rule (`sk = "rule#{antecedent}#{consequent}"`)

| Attribute | Type | Description |
|-----------|------|-------------|
| `record_type` | S | `"association_rule"` |
| `branch` | S | Branch name |
| `antecedents` | S | Food item (the trigger) |
| `consequents` | S | Beverage item (the upsell) |
| `support` | N | Fraction of orders containing both |
| `confidence` | N | P(consequent | antecedent) |
| `lift` | N | Association strength multiplier |
| `explanation` | S | Human-readable cross-sell insight |

### Record: Recommendation (`pk = "recommendation"`, `sk = "growth"`)

| Attribute | Type | Description |
|-----------|------|-------------|
| `record_type` | S | `"recommendation"` |
| `strategy` | S | e.g. `"Coffee & Milkshake Combo Uplift"` |
| `objective` | S | Strategy objective |
| `key_findings` | S | JSON array of finding strings |
| `branch_actions` | S | JSON array of `{branch, potential_score, action, ...}` |
| `explanation` | S | Human-readable strategy summary |

### Access Patterns

```python
# Get everything for a branch (KPI + growth potential + all rules)
table.query(KeyConditionExpression=Key("pk").eq("Conut Jnah"))

# Get just the beverage KPIs
table.get_item(Key={"pk": "Main Street Coffee", "sk": "beverage_kpi"})

# Get growth ranking for a branch
table.get_item(Key={"pk": "Conut Jnah", "sk": "growth_potential"})

# Get all association rules for a branch
table.query(
    KeyConditionExpression=Key("pk").eq("Conut Jnah") & Key("sk").begins_with("rule#")
)

# Get the overall growth recommendation
table.get_item(Key={"pk": "recommendation", "sk": "growth"})

# Find high-lift rules across all branches
table.scan(FilterExpression=Attr("lift").gte(Decimal("10.0")) & Attr("record_type").eq("association_rule"))
```

---

## Agent Query Cheat Sheet

Common questions the agent can answer and which table + query to use:

| Question | Table | Query |
|----------|-------|-------|
| "What's the forecast for Conut Jnah?" | forecast | `pk = "Conut Jnah#base"`, `sk = "period#1"` |
| "Which items go well together?" | combo | `pk = "overall"` → sort by lift |
| "Best combos at Conut Tyre?" | combo | `pk = "branch:Conut - Tyre"` |
| "Should we expand?" | expansion | `pk = "recommendation"`, `sk = "expansion"` |
| "How does Jnah perform?" | expansion | `pk = "jnah"`, `sk = "kpi"` |
| "Which branch is feasible?" | expansion | scan where `score_tier = "High"` |
| "Are we understaffed Friday night?" | staffing | `pk = "Conut Jnah"`, `sk begins_with "gap#Friday"` |
| "Staffing summary for Tyre?" | staffing | `pk = "Conut - Tyre"`, `sk = "findings"` |
| "Which branch needs more beverages?" | growth | `pk = "recommendation"`, `sk = "growth"` |
| "What to upsell at Jnah?" | growth | `pk = "Conut Jnah"`, `sk begins_with "rule#"` |
| "Beverage attachment rate?" | growth | get_item `sk = "beverage_kpi"` for each branch |

---

## Notes

- All numeric values are stored as DynamoDB `Number` type (Decimal).
- JSON objects (region_scores, growth_summary, branch_actions, key_findings) are
  stored as **stringified JSON** — parse with `json.loads()` before use.
- The `explanation` column on every item is designed for direct agent output —
  no formatting or calculation needed.
- Table billing mode: **PAY_PER_REQUEST** (on-demand) — no capacity planning needed.
- Environment suffix (`-dev`, `-prod`) is controlled by the CDK `env_name` parameter.
