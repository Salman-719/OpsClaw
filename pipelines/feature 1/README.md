# Feature 1 – Combo Optimization

Business Objective #1 from the Conut AI Engineering Hackathon.

## What it does

| Step | Description |
|------|-------------|
| Load | Reads a cleaned line-item CSV or Parquet (flexible schema) |
| Basket | Collapses rows → one basket per `order_id`, deduplicates items, infers `channel` if absent |
| Pairs | Generates all sorted item pairs per basket via vectorised self-join |
| Stats | Computes `support`, `confidence`, `lift` across **4 scopes**: overall / branch / channel / branch+channel |
| Filter | Applies `min_support` and `min_count_ab` thresholds |
| Validate | Runs assertions on metric ranges, count consistency, pair uniqueness, and basket pair-count |
| Save | Writes two Parquet artefacts (does not touch the source data) |

## Outputs

| File | Contents |
|------|----------|
| `data/processed/order_baskets.parquet` | One row per order: `order_id`, `branch`, `channel`, `items_set`, `n_items`, `day_of_week`, `hour`, `month` |
| `data/artifacts/combo_pairs.parquet`  | Pair statistics across all scopes; columns: `scope`, `item_a`, `item_b`, `n_orders`, `count_a`, `count_b`, `count_ab`, `support`, `confidence_ab`, `confidence_ba`, `lift` |

## Quick start

Make sure `pandas` and `pyarrow` are installed:

```bash
pip install pandas pyarrow
```

### Run against the project's existing pipeline output

```bash
# from the repo root
cd "pipelines/feature 1"

python src/features/combo_optimization.py \
  --in  "../../pipelines/output/transaction_baskets_raw_lines.csv" \
  --out_baskets  data/processed/order_baskets.parquet \
  --out_pairs    data/artifacts/combo_pairs.parquet \
  --min_support  0.01 \
  --min_count_ab 2
```

> **Tip:** the default `--min_count_ab 10` may filter everything out on small datasets.
> Lower it to `--min_count_ab 2` for the included test data (~122 baskets).

### Run against the raw delivery source CSV

```bash
python src/features/combo_optimization.py \
  --in  "../../conut_bakery_scaled_data/sales_by_customer_detail_delivery.csv" \
  --out_baskets  data/processed/order_baskets.parquet \
  --out_pairs    data/artifacts/combo_pairs.parquet \
  --min_support  0.01 \
  --min_count_ab 2
```

### Skip validation

```bash
python src/features/combo_optimization.py \
  --in  path/to/line_items.csv \
  --no_validate
```

## Accepted input schemas

The loader auto-detects three formats:

| Format | Required columns |
|--------|-----------------|
| Generic cleaned line-items | `order_id` (or `basket_id`), `item`, `branch`; optionally `channel`, `timestamp` |
| `transaction_baskets_raw_lines.csv` | `basket_id`, `branch`, `customer`, `item`, `qty`, `price` |
| `transaction_baskets_basket_core.csv` | `basket_id`, `branch`, `customer`, `items_list`, … |

## Programmatic usage

```python
from src.features.combo_optimization import run

baskets, pairs = run(
    in_path      = "pipelines/output/transaction_baskets_raw_lines.csv",
    out_baskets  = "data/processed/order_baskets.parquet",
    out_pairs    = "data/artifacts/combo_pairs.parquet",
    min_support  = 0.01,
    min_count_ab = 2,
)

# Top combos overall
overall = pairs[pairs["scope"] == "overall"].nlargest(10, "lift")

# Combos for a specific branch
branch_pairs = pairs[pairs["scope"] == "branch:Conut - Tyre"]

# All combos containing a specific item
item = "CLASSIC CHIMNEY"
item_pairs = pairs[(pairs["item_a"] == item) | (pairs["item_b"] == item)]
```

## Answering the four business questions

A dedicated query module [`src/features/combo_queries.py`](src/features/combo_queries.py)
maps each hackathon business question to a single CLI command or Python function call.

### Q1 — What are the top-performing combos overall?

```bash
python src/features/combo_queries.py --question top_overall --top 10 --rank_by lift
```

### Q2 — What are the top combos per branch?

```bash
# All branches
python src/features/combo_queries.py --question top_per_branch --top 5

# Specific branch
python src/features/combo_queries.py --question top_per_branch --branch "Conut Jnah" --top 10
```

### Q3 — What are the top combos per channel?

```bash
# All channels
python src/features/combo_queries.py --question top_per_channel --top 5

# Delivery only
python src/features/combo_queries.py --question top_per_channel --channel DELIVERY --top 10
```

### Q4 — What items strongly pair with X?

```bash
python src/features/combo_queries.py --question pairs_with --item "CLASSIC CHIMNEY"

# Search across all scopes
python src/features/combo_queries.py --question pairs_with --item "CHIMNEY" --scope all --top 15
```

All commands accept `--rank_by lift|support|count_ab` and `--min_count N`.

### Python API

```python
from src.features.combo_queries import (
    top_combos_overall,
    top_combos_per_branch,
    top_combos_per_channel,
    combos_with_item,
)

top_combos_overall(top=10, rank_by="lift")
top_combos_per_branch(branch="Conut Jnah", top=5)
top_combos_per_channel(channel="DELIVERY", top=10)
combos_with_item("CLASSIC CHIMNEY", scope="overall", top=10)
```

## Agent query reference

See the docstring at the top of `src/features/combo_optimization.py` for the full
**ARTIFACT SCHEMA** and **AGENT QUERY GUIDE** — Pandas query patterns that a
downstream agent can execute directly against `combo_pairs.parquet`.
