# ETL Pipeline

> Data ingestion and transformation pipeline that processes raw Conut bakery CSV exports into clean, analytics-ready datasets.

---

## Overview

The ETL pipeline lives in the `pipelines/` directory and handles:

1. **Auto-detection** of CSV report types via content-based signature matching
2. **Parsing** of 6 different Omega POS report formats
3. **Building** dimension tables, reconciliation checks, and feature stores
4. **Output** of 15 clean CSV files ready for analytics

## Architecture

```
Raw CSVs (any filename)
    │
    ▼
┌──────────────────────┐
│  detect_report_type() │  ← Reads first 5 lines, matches 6 signatures
└──────────┬───────────┘
           │
    ┌──────┴──────┐
    │  6 Parsers  │
    └──────┬──────┘
           │
    ┌──────┴──────────────┐
    │  Post-parse layers  │
    │  - Dimensions       │
    │  - Reconciliation   │
    │  - Feature store    │
    └──────┬──────────────┘
           │
    ┌──────┴──────┐
    │  15 CSVs    │ → pipelines/output/
    └─────────────┘
```

## File Structure

```
pipelines/
├── run_pipeline.py          # Main orchestrator
├── __init__.py
├── parsers/
│   ├── __init__.py
│   ├── utils.py             # Shared utilities (detection, parsing, classification)
│   ├── monthly_sales.py     # Parser 1: Monthly Sales by Branch
│   ├── items_by_group.py    # Parser 2: Sales by Items by Group
│   ├── avg_sales_menu.py    # Parser 3: Average Sales by Menu
│   ├── customer_orders.py   # Parser 4: Customer Orders (Delivery)
│   ├── transaction_baskets.py # Parser 5: Sales by Customer in Details
│   ├── attendance.py        # Parser 6: Time & Attendance
│   ├── dimensions.py        # Dimension table builders
│   ├── reconciliation.py    # Cross-report reconciliation checks
│   └── features.py          # Feature store builders
└── output/                  # Generated CSVs (15 files)
```

## Report Detection

Detection is **content-based**, not filename-based. The pipeline reads the first 5 lines of each CSV and matches against 6 signature phrases:

| Signature Phrase | Report Type Key | Parser |
|------------------|-----------------|--------|
| `monthly sales` | `monthly_sales` | `monthly_sales.py` |
| `sales by items by group` | `items_by_group` | `items_by_group.py` |
| `average sales by menu` | `avg_sales_menu` | `avg_sales_menu.py` |
| `customer orders (delivery)` | `customer_orders` | `customer_orders.py` |
| `sales by customer in details` | `transaction_baskets` | `transaction_baskets.py` |
| `time & attendance` | `attendance` | `attendance.py` |

This means **files can be named anything** — the pipeline detects what they are from their content headers.

## Parsers

### Parser 1: Monthly Sales (`monthly_sales.py`)

- **Input:** Monthly revenue summary per branch
- **Output:** `monthly_sales.csv`
- **Columns:** `branch`, `month`, `year`, `date`, `revenue`, `is_partial_history`
- **Use:** Branch-level revenue source of truth, trend analysis, momentum

### Parser 2: Items by Group (`items_by_group.py`)

- **Input:** Sales broken down by item group per branch
- **Output:** `items_by_group.csv`
- **Columns:** `branch`, `group`, `item`, `qty`, `amount`
- **Use:** Product-level analysis, group performance

### Parser 3: Average Sales by Menu (`avg_sales_menu.py`)

- **Input:** Menu item average sales data
- **Output:** `avg_sales_menu.csv`
- **Columns:** `branch`, `item`, `qty`, `amount`, `avg_price`
- **Use:** Menu optimization, pricing analysis

### Parser 4: Customer Orders (`customer_orders.py`)

- **Input:** Delivery customer order data
- **Output:** `customer_orders.csv`
- **Columns:** `branch`, `customer`, `orders`, `total`, `avg_order`
- **Use:** Customer segmentation, delivery analysis

### Parser 5: Transaction Baskets (`transaction_baskets.py`)

- **Input:** Detailed transaction-level sales data
- **Output:** Three files:
  - `transaction_baskets_raw_lines.csv` — Raw transaction lines
  - `transaction_baskets_audit_lines.csv` — Audit trail
  - `transaction_baskets_basket_core.csv` — Cleaned basket data
- **Use:** Market basket analysis, combo optimization (Feature 1)

### Parser 6: Attendance (`attendance.py`)

- **Input:** Employee time & attendance records
- **Output:** `attendance.csv`
- **Columns:** `branch`, `employee`, `date`, `shift`, `hours`, `day_of_week`
- **Use:** Staffing analysis (Feature 4)

## Post-Parse Layers

After parsing, the pipeline builds additional derived tables:

### Dimension Tables

| Output | Builder | Description |
|--------|---------|-------------|
| `dim_branch.csv` | `build_dim_branch()` | Branch dimension (from avg_sales, monthly_sales, attendance) |
| `dim_item.csv` | `build_dim_item()` | Item dimension (from items_by_group) |

### Reconciliation

| Output | Builder | Description |
|--------|---------|-------------|
| `fact_reconciliation_checks.csv` | `build_reconciliation()` | Cross-report consistency checks |

### Feature Store

| Output | Builder | Description |
|--------|---------|-------------|
| `feat_branch_month.csv` | `build_feat_branch_month()` | Branch × month aggregates |
| `feat_branch_item.csv` | `build_feat_branch_item()` | Branch × item aggregates |
| `feat_customer_delivery.csv` | `build_feat_customer_delivery()` | Customer delivery features |
| `feat_branch_shift.csv` | `build_feat_branch_shift()` | Branch shift staffing features |

## Pipeline Safeguards

- **Duplicate detection:** Files with identical content hashes are skipped
- **Two-phase validation:** `detect_report_type()` identifies the type, then `parser.can_parse()` double-checks
- **Error isolation:** Each parser and post-parse layer runs in its own try/except block
- **Encoding fallback:** Tries UTF-8, Latin-1, CP1252 in sequence

## Running Locally

```bash
# Default: uses bundled sample data
python pipelines/run_pipeline.py

# Custom data directory
python pipelines/run_pipeline.py --data-dir /path/to/csvs
```

## Output

The pipeline produces **up to 15 CSV files** in `pipelines/output/`:

```
pipelines/output/
├── monthly_sales.csv
├── items_by_group.csv
├── avg_sales_menu.csv
├── customer_orders.csv
├── transaction_baskets_raw_lines.csv
├── transaction_baskets_audit_lines.csv
├── transaction_baskets_basket_core.csv
├── attendance.csv
├── dim_branch.csv
├── dim_item.csv
├── fact_reconciliation_checks.csv
├── feat_branch_month.csv
├── feat_branch_item.csv
├── feat_customer_delivery.csv
└── feat_branch_shift.csv
```

## Lambda Integration

In production, the ETL runs as a **Docker Lambda function** (`infra/handlers/etl_handler.py`):

1. Downloads all CSVs from `s3://<bucket>/input/`
2. Runs `pipelines.run_pipeline.run()` in a temp directory
3. Uploads 15 output CSVs to `s3://<bucket>/processed/`
4. Returns the list of uploaded S3 keys for the next Step Functions stage

The Lambda uses a multi-stage Docker image (`infra/Dockerfile`, `etl` target) with Python 3.13 and all dependencies.
