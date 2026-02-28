# Conut Data Extraction Pipeline — Technical Documentation

## Overview

This pipeline processes **raw CSV exports from the Omega POS system** used by Conut bakery (4 branches). The CSVs are report-style files with multi-line headers/footers, page breaks, repeated column headers, and comma-formatted numbers in quoted strings.

All parsing is **pattern-based** — branch names, dates, and section headers are detected by shape (regex), not by hardcoded values. The pipeline adapts automatically to new branches, items, or employees.

### Design Principles

- **Source-of-truth hierarchy**: each file is trusted for specific metrics — not all data is equally reliable for every purpose.
- **Feature-ready outputs**: the pipeline goes beyond cleaning into a reusable analytics layer.
- **Modeling guardrails**: each parser documents what the data can and cannot be used for.

---

## Architecture

```
pipelines/
├── run_pipeline.py              # Orchestrator: discover → detect → parse → enrich → save
├── output/                      # All outputs (15 CSVs)
└── parsers/
    ├── __init__.py
    ├── utils.py                 # Shared utilities
    ├── monthly_sales.py         # Pipeline 1
    ├── items_by_group.py        # Pipeline 2
    ├── avg_sales_menu.py        # Pipeline 3
    ├── customer_orders.py       # Pipeline 4
    ├── transaction_baskets.py   # Pipeline 5
    ├── attendance.py            # Pipeline 6
    ├── dimensions.py            # dim_branch, dim_item builders
    ├── reconciliation.py        # Cross-source validation
    └── features.py              # Feature store (4 feature tables)
```

### Auto-detection Flow

1. `run_pipeline.py` scans the data directory for `*.csv` files.
2. Duplicate files are skipped via content hash (first 8 KB, MD5).
3. For each file, `utils.detect_report_type()` checks the first 5 lines against known signature phrases.
4. The matching parser module's `can_parse(lines)` is called for confirmation.
5. `parser.parse(filepath)` returns one or more `pd.DataFrame`s.
6. Post-parse layers build dimension tables, reconciliation checks, and feature tables.
7. All DataFrames are saved to `pipelines/output/` as clean CSVs.

---

## Shared Utilities — `utils.py`

| Function | Purpose |
|---|---|
| `parse_number(value)` | Strip quotes, commas, whitespace → `float` or `None` |
| `is_page_break(line)` | Matches `Page X of Y` |
| `is_date_line(line)` | Matches `DD-Mon-YY` at line start (report print dates) |
| `is_copyright(line)` | Matches Omega POS copyright/footer lines |
| `is_total_line(line)` | Matches lines starting with `Total` |
| `is_blank(line)` | All commas / whitespace only |
| `is_noise(line)` | Union of page-break, copyright, blank |
| `parse_csv_line(line)` | Python `csv.reader` on a single line, returns `list[str]` |
| `read_lines(filepath)` | Multi-encoding reader (UTF-8 → Latin-1 → CP1252) |
| `looks_like_standalone_label(cells)` | First cell has text, rest empty (branch/section header) |
| `detect_report_type(lines)` | Signature-matching on first 5 lines → type key or `None` |

---

## Source-of-Truth Hierarchy

| Metric | Trusted Source | Do NOT use |
|---|---|---|
| Branch revenue | `monthly_sales` | items_by_group (mix only) |
| Channel mix | `avg_sales_menu` | — |
| Product mix / ranking | `items_by_group` | monthly_sales (no product detail) |
| Staffing patterns | `attendance` (valid shifts) | — |
| Delivery customer behaviour | `customer_orders` (phone as key) | — |
| Basket co-purchase | `transaction_baskets_basket_core` | — |

---

## Pipeline 1 — Monthly Sales by Branch

**Source:** `monthly_sales_by_branch.csv`
**Output:** `monthly_sales.csv`

**Use for:** trend, recent momentum, volatility, branch demand index.
**Do NOT use for:** seasonality (only 4–5 months of data).

### Extraction Logic

1. Identify branch headers via regex `^Branch\s*Name\s*:\s*(.+)`.
2. Skip noise lines (page breaks, copyright, blank, column headers matching `^Month,`).
3. Parse data rows: `month_name, _, year, revenue`.
4. Validate month names against a dictionary (January–December).
5. Synthesize `month_num` and `date` (`YYYY-MM-01`) for time-series operations.
6. Flag `is_partial_history` for branches with fewer months than the maximum observed.
7. Sort by `(branch, date)`.

### Schema

| Column | Type | Description |
|---|---|---|
| `branch` | str | Branch name |
| `month` | str | Full month name |
| `year` | int | Calendar year |
| `revenue` | float | Monthly revenue (LBP, scaled) |
| `month_num` | int | 1–12 |
| `date` | date | First of month |
| `is_partial_history` | bool | True if branch has fewer months than the max (Main Street Coffee) |

### Stats
- 19 rows, 4 branches × 5 months (Aug–Dec 2025)
- Main Street Coffee has 4 months (flagged `is_partial_history=True`)

---

## Pipeline 2 — Sales by Items and Groups

**Source:** `sales_by_items_and_groups.csv`
**Output:** `items_by_group.csv`

**Use for:** product mix, ranking, share, category importance, cross-sell inputs.
**Do NOT use for:** branch-level revenue truth.

### Extraction Logic

1. Detect hierarchy headers via regex: `^Branch\s*:`, `^Division\s*:`, `^Group\s*:`.
2. Track current `branch → division → group` context as a state machine.
3. Parse data rows: `item_description, barcode, qty, amount`.
4. Derive `is_modifier`: items with `amount == 0` and `qty > 0` (toppings, add-ons).
5. Assign 6-tier `category` via regex on division name.
6. Compute `item_sales_share_within_branch`, `item_rank_within_branch`, `item_rank_within_division` on non-modifier items.

### Schema

| Column | Type | Description |
|---|---|---|
| `branch` | str | Branch name |
| `division` | str | Top-level division |
| `group` | str | Sub-group |
| `item` | str | Item description |
| `qty` | float | Quantity sold |
| `amount` | float | Revenue (LBP, scaled) |
| `is_modifier` | bool | True if zero-revenue modifier/add-on |
| `category` | str | `coffee_hot`, `coffee_cold`, `milkshake`, `other_beverage`, `core_food`, `modifier` |
| `item_sales_share_within_branch` | float | Share of branch paid revenue |
| `item_rank_within_branch` | int | Dense rank by revenue within branch |
| `item_rank_within_division` | int | Dense rank by revenue within branch×division |

### Category Logic
- `coffee_hot` — division matches `hot.?coffee`
- `coffee_cold` — division matches `frappes?|iced.?coffee|cold.?brew`
- `milkshake` — division matches `shakes?|milkshakes?`
- `other_beverage` — division matches `juice|lemonade|tea|smoothie|drink|mojito`
- `modifier` — `is_modifier=True` (amount=0, qty>0)
- `core_food` — everything else

### Stats
- 1,158 rows: 540 core_food, 395 modifier, 90 coffee_hot, 52 other_beverage, 41 milkshake, 40 coffee_cold
- Share and rank columns: computed on non-modifier items only

---

## Pipeline 3 — Average Sales by Menu (Channel KPIs)

**Source:** `average_sales_by_menu.csv`
**Output:** `avg_sales_menu.csv`

**Use for:** branch archetyping, channel dependence, avg ticket, promo targeting.
**Treat as:** branch-channel aggregate (not a time series).

### Extraction Logic

1. Detect branch headers via `looks_like_standalone_label()` (first cell has text, rest empty).
2. Match data rows where first cell matches known channel pattern: `DELIVERY|TABLE|TAKE\s*AWAY`.
3. Parse: `channel, customers, sales, avg_per_customer`.
4. Compute `sales_share_within_branch` and `customer_share_within_branch`.

### Schema

| Column | Type | Description |
|---|---|---|
| `branch` | str | Branch name |
| `channel` | str | `DELIVERY`, `TABLE`, `TAKE AWAY` |
| `customers` | float | Customer count |
| `sales` | float | Total sales (LBP, scaled) |
| `avg_per_customer` | float | Average ticket |
| `sales_share_within_branch` | float | Channel's share of branch revenue |
| `customer_share_within_branch` | float | Channel's share of branch customers |

### Stats
- 7 rows across 4 branches (not all have all channels)

---

## Pipeline 4 — Customer Orders (Delivery)

**Source:** `customer_orders_delivery.csv`
**Output:** `customer_orders.csv`

**Use for:** recency, frequency, spend tier, repeat rate, active span.
**Do NOT use for:** monthly acquisition series or delivery volume trend (no per-order timestamps).
**Key design decision:** `phone` is the canonical customer identifier (not `Person_XXXX`).

### Extraction Logic

1. Detect branch headers: standalone text matching `^[A-Z][A-Za-z\s\-'']+$` with rest of cells empty.
2. Identify data rows via `Person_\d+` regex.
3. Extract fields using regex: phone, datetime pairs, quoted numbers, small integers.
4. Derive `is_zero_value_customer` (total=0 — could be refund, test profile, or void).
5. Compute `recency_days`, `customer_lifespan_days`, `avg_order_value`, `is_repeat_customer`.
6. Sort by `(branch, last_order DESC)`.

### Schema

| Column | Type | Description |
|---|---|---|
| `branch` | str | Branch name |
| `customer` | str | Anonymized label (`Person_XXXX`) |
| `phone` | str | Phone number (canonical customer key) |
| `first_order` | datetime | Earliest order timestamp |
| `last_order` | datetime | Latest order timestamp |
| `total` | float | Total spend |
| `num_orders` | int | Number of orders |
| `is_zero_value_customer` | bool | True if total=0 (could be refund, test, void) |
| `recency_days` | int | Days since last order (relative to latest in dataset) |
| `customer_lifespan_days` | int | Days between first and last order |
| `avg_order_value` | float | total / num_orders |
| `is_repeat_customer` | bool | True if num_orders > 1 |

### Stats
- 539 rows: 515 active, 24 zero-value
- All 4 branches

---

## Pipeline 5 — Transaction Baskets (Delivery Detail)

**Source:** `sales_by_customer_detail_delivery.csv`
**Outputs:** 3 tables

**Use for:** co-purchase tendency, delivery bundle ideas (Apriori / FP-Growth).
**Key design decision:** Each `Person_XXXX → Total` report block = one basket. NOT all items per customer merged.

### Critical Change from v1
The previous version grouped all items per customer into one basket, which merged separate orders and created false associations. Now each report block gets a unique `basket_id`.

### Extraction Logic

1. Detect `Branch : <name>` headers via regex.
2. Detect customer headers: lines matching `^Person_\d+`.
3. Each customer header increments `basket_id` (new basket boundary).
4. Parse line items: rows with empty first cell → `qty, item, price`.
5. Build three output tables with progressive filtering.

### Table A: `transaction_baskets_raw_lines.csv`

| Column | Type | Description |
|---|---|---|
| `branch` | str | Branch name |
| `customer` | str | Person label |
| `basket_id` | int | Unique per report block |
| `item` | str | Item description |
| `qty` | float | Quantity |
| `price` | float | Line price |

### Table B: `transaction_baskets_audit_lines.csv`

Same as raw_lines plus:

| Column | Type | Description |
|---|---|---|
| `is_void` | bool | True if qty < 0 |
| `is_modifier` | bool | True if price=0 and not void |

### Table C: `transaction_baskets_basket_core.csv`

Core paid items only (modifiers and voids excluded) — ready for Apriori/FP-Growth.

| Column | Type | Description |
|---|---|---|
| `basket_id` | int | Unique basket |
| `branch` | str | Branch name |
| `customer` | str | Person label |
| `items_list` | list[str] | Paid items in basket |
| `unique_items` | int | Distinct paid items |
| `net_qty` | float | Total non-void quantity |
| `net_total` | float | Total non-void revenue |

### Stats
- 1,881 raw lines, 121 core baskets (3 branches; Conut main has no detail data)
- Period: January 2026

---

## Pipeline 6 — Time & Attendance

**Source:** `time_and_attendance_logs.csv`
**Output:** `attendance.csv`

**Use for:** rules-based / pattern-based / archetype-based staffing models.
**Key design decisions:**
- Anomalous shifts are **flagged, not deleted** — keep for audit, exclude from primary model.
- Thresholds are configurable: `TOO_SHORT_THRESHOLD=2h`, `TOO_LONG_THRESHOLD=14h`.

### Extraction Logic

1. **Two-pass approach**:
   - **Pass 1**: Discover branch names dynamically. After each `EMP ID:` line, the next non-empty non-date cell is a branch name.
   - **Pass 2**: Full parse using discovered branch set.
2. Extract employee headers via `EMP ID:\s*([\d.]+)` and `NAME:\s*(Person_\d+)`.
3. Branch assignment: match cells against the set discovered in pass 1.
4. Parse data rows: lines containing `DD-Mon-YY` dates and `HH.MM.SS` times.
5. Derive `shift_type` from punch-in hour: morning (<12), afternoon (12–16), evening (≥17).
6. Flag `is_anomalous` if duration < 2h or > 14h. Set `is_valid_shift` accordingly.
7. Derive `day_of_week` and `weekend_flag`.

### Schema

| Column | Type | Description |
|---|---|---|
| `emp_id` | str | Employee ID |
| `name` | str | `Person_XXXX` |
| `branch` | str | Branch name |
| `date` | date | Shift date |
| `punch_in` | str | `HH:MM:SS` |
| `punch_out` | str | `HH:MM:SS` |
| `duration_hours` | float | Decimal hours |
| `shift_type` | str | `morning` (<12), `afternoon` (12–16), `evening` (≥17) |
| `is_anomalous` | bool | Duration outside 2–14h range |
| `is_valid_shift` | bool | Not anomalous and has duration |
| `shift_start_hour` | int | Hour of punch_in (0–23) |
| `day_of_week` | str | Day name |
| `weekend_flag` | bool | Saturday or Sunday |

### Stats
- 311 shifts, 3 branches (Conut main not in data)
- 55 anomalous shifts (~18%) — flagged, not dropped
- Shift distribution: 177 afternoon, 107 morning, 27 evening

---

## Dimension Tables

### `dim_branch.csv`

Built from `avg_sales_menu`, `monthly_sales`, and `attendance` outputs.

| Column | Type | Description |
|---|---|---|
| `canonical_branch_name` | str | Standard branch name |
| `has_delivery` | bool | Offers delivery channel |
| `has_table` | bool | Offers table/dine-in |
| `has_takeaway` | bool | Offers take-away |
| `has_monthly_sales` | bool | In monthly sales data |
| `months_of_data` | int | Number of months available |
| `has_attendance_data` | bool | In attendance data |

### `dim_item.csv`

Built from `items_by_group` output. One row per unique item (first occurrence's hierarchy).

| Column | Type | Description |
|---|---|---|
| `canonical_item_name` | str | Item description |
| `division` | str | Division (first occurrence) |
| `group` | str | Group (first occurrence) |
| `category` | str | 6-tier category |
| `modifier_flag` | bool | True if ever appears as modifier |
| `beverage_flag` | bool | True if category is any beverage type |

---

## Reconciliation Layer — `fact_reconciliation_checks.csv`

Cross-validates overlapping metrics between sources to enforce the trust hierarchy.

| Column | Description |
|---|---|
| `branch` | Branch being checked |
| `source_a` | Primary (trusted) source |
| `source_b` | Secondary source |
| `metric` | What's being compared |
| `value_a`, `value_b` | Values from each source |
| `variance_pct` | Absolute percentage variance |
| `is_within_tolerance` | Within 10% threshold |
| `note` | Explains which source to prefer |

### Current Checks
1. **monthly_sales vs avg_sales_menu** — branch revenue: within tolerance for most branches
2. **monthly_sales vs items_by_group** — branch revenue: diverges (items is mix data, not revenue truth)
3. **avg_sales_menu vs items_by_group** — cross-check: variable

---

## Feature Store

### `feat_branch_month.csv`

Branch-level demand features for forecasting and expansion analysis.

| Column | Description |
|---|---|
| `revenue_ma3` | 3-month moving average |
| `mom_growth` | Month-over-month growth rate |
| `volatility` | Expanding std of growth |
| `channel_delivery_share` | Delivery % of branch revenue (from avg_sales) |
| `beverage_share` | Beverage % of branch product mix (from items) |
| Plus all `monthly_sales.csv` columns |

### `feat_branch_item.csv`

Item-level features for combo optimization and growth strategy.

| Column | Description |
|---|---|
| `item_share` | % of branch paid revenue |
| `item_rank` | Dense rank by revenue |
| `attach_tendency` | Item's qty share (how often it's added) |
| `beverage_opportunity_flag` | True for non-beverage items (pairing candidates) |
| Plus item identifiers, category, qty, amount |

### `feat_customer_delivery.csv`

RFM-style customer features for delivery analysis.

| Column | Description |
|---|---|
| `value_segment` | `low`, `medium`, `high` (percentile-based within branch) |
| Plus all `customer_orders.csv` columns |

### `feat_branch_shift.csv`

Staffing features per branch (valid shifts only).

| Column | Description |
|---|---|
| `median_hours` | Median shift duration |
| `mean_hours` | Mean shift duration |
| `valid_shifts` | Count of non-anomalous shifts |
| `unique_employees` | Distinct employees |
| `morning_pct`, `afternoon_pct`, `evening_pct` | Shift type mix |
| `weekend_shift_pct` | Weekend shift proportion |
| `total_shifts` | All shifts including anomalous |
| `anomaly_rate` | Proportion flagged anomalous |

---

## Downstream Use (Hackathon Objectives)

| Objective | Primary Data | Feature Table | Supporting |
|---|---|---|---|
| **Combo Optimization** | `basket_core` (Apriori) | `feat_branch_item` | `dim_item` |
| **Demand Forecasting** | `monthly_sales` | `feat_branch_month` | `dim_branch` |
| **Expansion Feasibility** | `monthly_sales` + `avg_sales_menu` | `feat_branch_month` | `dim_branch`, reconciliation |
| **Shift Staffing** | `attendance` | `feat_branch_shift` | `dim_branch` |
| **Coffee/Milkshake Growth** | `items_by_group` (category filter) | `feat_branch_item` | `dim_item` |

---

## Known Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| 4–5 months data | No reliable seasonality | Use trend, MA, volatility only |
| Scaled/arbitrary LBP units | Absolute values are meaningless | Focus on ratios, ranks, shares |
| Attendance covers 3/4 branches | No staffing data for Conut main | Transfer by archetype |
| Transaction baskets cover 3/4 branches | No basket data for Conut main | Combo models limited to covered branches |
| Baskets span Jan 2026, rest is 2025 | Cannot cross-join periods | Treat independently |
| 55 anomalous attendance shifts | ~18% unreliable durations | `is_valid_shift=False`, kept for audit |
| 24 zero-value delivery customers | Unknown cause (refund/test/void) | `is_zero_value_customer=True` |
| items_by_group ≠ monthly_sales revenue | Product file is mix data | See reconciliation checks |
