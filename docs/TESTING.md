# Testing

> Unit and integration test suite covering the ETL pipeline, FastAPI agent service, and CDK infrastructure stacks.

---

## Overview

The project has **29 tests** across 3 test files:

| File | Tests | Coverage |
|------|-------|----------|
| `tests/test_pipeline.py` | 7 | ETL report detection, parser registry, full integration run |
| `tests/test_agent.py` | 15 | Health endpoint, chat, dashboard (6), upload (4), models (4) |
| `tests/test_infra.py` | 7 | CDK stack synthesis — resource counts, properties, exports |

---

## Running Tests

### Prerequisites

```bash
# Activate Python venv
source .venv/bin/activate

# Install test dependencies
pip install pytest httpx
```

### Run All Tests

```bash
python -m pytest tests/ -v
```

### Run Specific Test Files

```bash
# ETL pipeline tests
python -m pytest tests/test_pipeline.py -v

# Agent service tests
python -m pytest tests/test_agent.py -v

# Infrastructure tests
python -m pytest tests/test_infra.py -v
```

### Run with Short Traceback

```bash
python -m pytest tests/ -v --tb=short --color=yes
```

---

## Test Details

### ETL Pipeline Tests (`test_pipeline.py`)

```python
class TestDetectReportType:
    test_known_type_returns_key        # "Monthly Sales Summary" → "monthly_sales"
    test_unknown_returns_none          # Random text → None
    test_attendance_detected           # "Time & Attendance Report" → "attendance"
    test_items_by_group_detected       # "Sales by Items by Group" → "items_by_group"

class TestRunPipeline:
    test_output_dir_exists             # OUTPUT_DIR is a valid Path
    test_registry_has_all_parsers      # All 6 parser keys registered
    test_run_with_real_data            # Full ETL integration (uses sample data)
```

**Key:** `test_run_with_real_data` is an **integration test** that runs the complete ETL pipeline on the bundled `conut_bakery_scaled_data/` directory and verifies all output CSVs are created.

### Agent Service Tests (`test_agent.py`)

Tests use `FastAPI TestClient` with `LOCAL_MODE=true`:

```python
class TestHealth:
    test_health_returns_ok             # GET /api/health → 200, status: ok
    test_health_reports_local_mode     # local_mode: true

class TestChat:
    test_chat_requires_message         # POST /api/chat {} → 422
    test_chat_empty_message_rejected   # POST /api/chat {message: ""} → 422
    test_chat_returns_answer           # POST /api/chat {message: "hello"} → 200 + answer

class TestDashboard:
    test_overview                      # GET /api/dashboard/overview → 5 keys
    test_forecast                      # GET /api/dashboard/forecast → feature: forecast
    test_combo                         # GET /api/dashboard/combo → feature: combo
    test_expansion                     # GET /api/dashboard/expansion → feature: expansion
    test_staffing                      # GET /api/dashboard/staffing → feature: staffing
    test_growth                        # GET /api/dashboard/growth → feature: growth

class TestUpload:
    test_presign_blocked_in_local_mode   # POST /api/upload/presign → 400
    test_trigger_blocked_in_local_mode   # POST /api/upload/trigger → 400
    test_status_blocked_in_local_mode    # POST /api/upload/status → 400
    test_prepare_blocked_in_local_mode   # POST /api/upload/prepare → 400

class TestModels:
    test_chat_request_validation       # ChatRequest(message="test") works
    test_chat_request_max_length       # ChatRequest(message="x"*2001) fails
    test_dashboard_section             # DashboardSection fields valid
    test_tool_call_info                # ToolCallInfo fields valid
```

**Key behaviors:**
- Chat endpoint in LOCAL_MODE uses keyword-based tool dispatch (no Bedrock)
- Upload endpoints return 400 in LOCAL_MODE (S3/StepFunctions not available)
- Dashboard endpoints read from local CSV fallback

### Infrastructure Tests (`test_infra.py`)

Tests use CDK `Template.from_stack()` assertions:

```python
class TestPipelineStack:
    test_s3_bucket_created            # 1 S3 bucket
    test_dynamodb_tables_count        # 5 DynamoDB tables
    test_lambda_functions_count       # 6 Lambda functions
    test_state_machine_created        # 1 Step Functions state machine
    test_bucket_has_versioning        # Versioning: Enabled
    test_tables_use_pay_per_request   # BillingMode: PAY_PER_REQUEST
    test_exports_data_bucket          # Stack has data_bucket + state_machine

class TestAgentStack:
    test_ec2_instance_created         # 1 EC2 instance
    test_instance_type_is_t3_small    # t3.small
    test_alb_created                  # 1 ALB
    test_vpc_created                  # 1 VPC
    test_has_iam_role                 # ec2.amazonaws.com service principal

class TestFrontendStack:
    test_s3_bucket_created            # 1 S3 bucket
    test_cloudfront_distribution_created  # 1 CloudFront distribution
    test_spa_error_responses          # 404→200 /index.html, 403→200 /index.html
```

---

## CI Integration

Tests run automatically in GitHub Actions on every push and PR to `main`:

```yaml
- name: Run Python unit tests
  env:
    LOCAL_MODE: "true"
  run: |
    python -m pytest tests/test_pipeline.py tests/test_agent.py -v --tb=short --color=yes
```

> **Note:** `test_infra.py` is not included in CI by default to avoid Docker build dependencies. Add it if your CI environment supports Docker.

---

## Environment Requirements

| Test File | Requires | Notes |
|-----------|----------|-------|
| `test_pipeline.py` | pandas, sample data | Skips integration if data missing |
| `test_agent.py` | fastapi, httpx, LOCAL_MODE=true | No AWS access needed |
| `test_infra.py` | aws-cdk-lib, Docker (for synth) | CDK synthesis only, no deploy |

---

## Adding New Tests

1. Create a new test file in `tests/` (e.g., `test_analytics.py`)
2. Add `PROJECT_ROOT` path setup:
   ```python
   import sys
   from pathlib import Path
   PROJECT_ROOT = Path(__file__).resolve().parent.parent
   sys.path.insert(0, str(PROJECT_ROOT))
   ```
3. Use `pytest` classes and `assert` statements
4. Add to CI workflow if needed
