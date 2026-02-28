# Conut Data Pipeline — README

## Quick Start

```bash
# 1. Activate the virtual environment
source .venv/bin/activate

# 2. Run the full pipeline
python pipelines/run_pipeline.py

# 3. (Optional) Point to a different data directory
python pipelines/run_pipeline.py --data-dir /path/to/csvs
```

Default data directory: `Conut bakery Scaled Data /` (relative to project root).

## Requirements

- Python 3.11+
- pandas, numpy (installed in `.venv`)

```bash
python -m venv .venv
source .venv/bin/activate
pip install pandas numpy
```

## What It Does

1. **Discovers** all `.csv` files in the data directory.
2. **Deduplicates** by content hash (first 8 KB, MD5).
3. **Auto-detects** report type from the first 5 lines (signature matching).
4. **Parses** each file with the matching parser module.
5. **Builds** dimension tables, reconciliation checks, and feature tables.
6. **Saves** all outputs to `pipelines/output/`.

## Output Files (15 CSVs)

| Layer | File | Rows | Cols |
|---|---|---|---|
| Parser | `monthly_sales.csv` | 19 | 7 |
| Parser | `items_by_group.csv` | 1,158 | 11 |
| Parser | `avg_sales_menu.csv` | 7 | 7 |
| Parser | `customer_orders.csv` | 539 | 12 |
| Parser | `transaction_baskets_raw_lines.csv` | 1,881 | 6 |
| Parser | `transaction_baskets_audit_lines.csv` | 1,881 | 8 |
| Parser | `transaction_baskets_basket_core.csv` | 121 | 7 |
| Parser | `attendance.csv` | 311 | 13 |
| Dimension | `dim_branch.csv` | 4 | 7 |
| Dimension | `dim_item.csv` | 325 | 6 |
| Reconciliation | `fact_reconciliation_checks.csv` | 12 | 9 |
| Feature | `feat_branch_month.csv` | 19 | 12 |
| Feature | `feat_branch_item.csv` | 711 | 11 |
| Feature | `feat_customer_delivery.csv` | 547 | 13 |
| Feature | `feat_branch_shift.csv` | 3 | 11 |

## Project Structure

```
pipelines/
├── run_pipeline.py              # Orchestrator
├── README.md                    # This file (usage)
├── DOCUMENTATION.md             # Detailed technical docs
├── output/                      # Generated CSVs
└── parsers/
    ├── __init__.py
    ├── utils.py                 # Shared utilities (line classification, number parsing)
    ├── monthly_sales.py         # Pipeline 1: monthly revenue per branch
    ├── items_by_group.py        # Pipeline 2: item-level sales with hierarchy
    ├── avg_sales_menu.py        # Pipeline 3: channel KPIs per branch
    ├── customer_orders.py       # Pipeline 4: delivery customer profiles
    ├── transaction_baskets.py   # Pipeline 5: basket transactions (3 tables)
    ├── attendance.py            # Pipeline 6: shift records
    ├── dimensions.py            # dim_branch, dim_item builders
    ├── reconciliation.py        # Cross-source validation checks
    └── features.py              # Feature store (4 feature tables)
```

## Adding a New Parser

1. Create `parsers/my_parser.py` with `can_parse(lines) -> bool` and `parse(filepath) -> pd.DataFrame`.
2. Add a signature to `utils.detect_report_type()`.
3. Register it in `run_pipeline.py`'s `REGISTRY` dict.

## Skipped Files

| File | Reason |
|---|---|
| `average_sales_by_menu_duplicate.csv` | Content-identical duplicate (auto-detected) |
| `tax_summary_by_branch.csv` | Unrecognized report type; derivable from monthly_sales × ~11% |
| `summary_by_division_menu_channel.csv` | Dropped — TOTAL column ~32% off from channel sum |

## Detailed Documentation

See [DOCUMENTATION.md](DOCUMENTATION.md) for full schema definitions, extraction logic, design decisions, source-of-truth hierarchy, reconciliation checks, feature store details, and known limitations.
