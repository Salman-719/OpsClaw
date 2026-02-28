# DynamoDB Schema Reference

> Complete schema for all 5 DynamoDB tables used by the OpsClaw agent.

---

## Table Overview

| Table | PK Name | SK Name | Billing | Purpose |
|-------|---------|---------|---------|---------|
| `conut-ops-forecast-dev` | `pk` | `sk` | PAY_PER_REQUEST | Demand forecast predictions |
| `conut-ops-combo-dev` | `pk` | `sk` | PAY_PER_REQUEST | Product combo association rules |
| `conut-ops-expansion-dev` | `pk` | `sk` | PAY_PER_REQUEST | Branch expansion feasibility |
| `conut-ops-staffing-dev` | `pk` | `sk` | PAY_PER_REQUEST | Shift staffing gap analysis |
| `conut-ops-growth-dev` | `pk` | `sk` | PAY_PER_REQUEST | Beverage growth strategy |

All tables use **string** type for both `pk` and `sk`.

---

## Forecast Table (`conut-ops-forecast-dev`)

| pk | sk | Attributes |
|----|-----|------------|
| `{branch}#{scenario}` | `period#{n}` | `predicted_orders`, `confidence`, `upper_bound`, `lower_bound`, `branch`, `scenario`, `period` |

**Examples:**
- `pk=Conut#base`, `sk=period#1` → 1-month base forecast for Conut
- `pk=Conut Jnah#optimistic`, `sk=period#3` → 3-month optimistic forecast for Jnah

**Scenarios:** `base`, `optimistic`
**Periods:** `1` (1-month), `2` (2-month), `3` (3-month)

---

## Combo Table (`conut-ops-combo-dev`)

| pk | sk | Attributes |
|----|-----|------------|
| Scope string | `{item_a}#{item_b}` | `support`, `confidence`, `lift`, `item_a`, `item_b`, `scope` |

**Scope formats:**
- `overall` — All branches combined
- `branch:{name}` — Single branch (e.g., `branch:Conut Jnah`)
- `channel:{type}` — Channel-specific

**Interpretation:**
- Lift > 3 = strong association
- Lift > 5 = very strong association

---

## Expansion Table (`conut-ops-expansion-dev`)

| pk | sk | Attributes |
|----|-----|------------|
| Branch name (lowercase) | `kpi` | `revenue`, `orders`, `avg_ticket`, `growth_rate`, `consistency`, etc. |
| Branch name (lowercase) | `feasibility` | `score` (0–1), `tier` (High/Medium/Low) |
| `recommendation` | `expansion` | `top_candidate`, `reasoning`, `score`, `tier` |

**Candidate branches:** `batroun`, `bliss`, `jnah`, `tyre`

**Tier thresholds:**
- High: score > 0.6
- Medium: 0.4 ≤ score ≤ 0.6
- Low: score < 0.4

---

## Staffing Table (`conut-ops-staffing-dev`)

| pk | sk | Attributes |
|----|-----|------------|
| Branch name | `findings` | `peak_hours`, `avg_gap`, `worst_day`, `recommendation`, etc. |
| Branch name | `gap#{day}#{hour}` | `demand`, `supply`, `gap`, `is_understaffed`, `day`, `hour` |

**Examples:**
- `pk=Conut Jnah`, `sk=findings` → Branch-level staffing summary
- `pk=Conut Jnah`, `sk=gap#Monday#09` → Gap at 9 AM on Monday

**Gap interpretation:**
- Gap > 0 → Understaffed (need more staff)
- Gap < 0 → Overstaffed (excess staff)
- Gap = 0 → Balanced

---

## Growth Table (`conut-ops-growth-dev`)

| pk | sk | Attributes |
|----|-----|------------|
| Branch name | `beverage_kpi` | `attachment_rate`, `beverage_share`, `beverage_count`, etc. |
| Branch name | `growth_potential` | `score`, `rank`, `benchmark_gap` |
| Branch name | `rule#{food_item}` | `lift`, `confidence`, `support`, `food_item`, `beverage_item` |
| `recommendation` | `growth` | `strategy`, `top_opportunity`, `reasoning` |

**Examples:**
- `pk=Conut Jnah`, `sk=beverage_kpi` → Beverage attachment metrics
- `pk=Conut Jnah`, `sk=rule#Croissant` → Croissant→beverage rule
- `pk=recommendation`, `sk=growth` → Overall growth strategy

---

## Query Patterns

### Single-item lookup
```python
table.get_item(Key={"pk": "Conut#base", "sk": "period#1"})
```

### Range query (all forecasts for a branch)
```python
table.query(
    KeyConditionExpression="pk = :pk",
    ExpressionAttributeValues={":pk": "Conut#base"}
)
```

### Full table scan (for rankings)
```python
table.scan()
```

### Filter by prefix
```python
table.query(
    KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
    ExpressionAttributeValues={":pk": "Conut Jnah", ":prefix": "gap#Monday"}
)
```
