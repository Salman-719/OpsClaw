"""
Demand-Forecast Lambda Handler
===============================
AWS Lambda entry-point that wraps the demand forecast pipeline.

Trigger modes:
  1. **Step Functions** — called after the ETL stage completes.
     Receives the S3 location of the processed CSVs.

  2. **Direct invoke** — on-demand re-forecast.
     Event schema:
       {
         "s3_bucket": "conut-data-<env>",
         "s3_processed_prefix": "processed/",
         "s3_results_prefix": "results/forecast/",
         "dynamodb_table": "conut-forecast-results"     # optional
       }

Environment variables (set in SAM template):
  S3_BUCKET              default bucket
  S3_PROCESSED_PREFIX    default "processed/"
  S3_RESULTS_PREFIX      default "results/forecast/"
  DYNAMODB_TABLE         table for agent queries (optional)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ── make project root importable ─────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── S3 helpers ───────────────────────────────────────────────────────────

def _s3_client():
    import boto3
    return boto3.client("s3")


def _download_processed(bucket: str, prefix: str, local_dir: Path) -> list[Path]:
    """Download processed CSVs that the forecast needs."""
    s3 = _s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    needed = {"monthly_sales.csv", "feat_branch_month.csv", "dim_branch.csv"}
    downloaded: list[Path] = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            fname = Path(key).name
            if fname in needed:
                local_path = local_dir / fname
                logger.info("  ↓ s3://%s/%s → %s", bucket, key, local_path)
                s3.download_file(bucket, key, str(local_path))
                downloaded.append(local_path)

    return downloaded


def _upload_results(local_dir: Path, bucket: str, prefix: str) -> list[str]:
    """Upload forecast output files to S3."""
    s3 = _s3_client()
    uploaded: list[str] = []

    for f in sorted(local_dir.rglob("*")):
        if f.is_dir():
            continue
        relative = f.relative_to(local_dir)
        key = f"{prefix}{relative}"
        logger.info("  ↑ %s → s3://%s/%s", relative, bucket, key)
        s3.upload_file(str(f), bucket, key)
        uploaded.append(key)

    return uploaded


def _write_to_dynamodb(table_name: str, forecast_csv: Path) -> int:
    """
    Write forecast rows to DynamoDB for agent querying.
    Each row becomes one item keyed by (branch, scenario, forecast_period).
    Returns count of items written.
    """
    import boto3
    import pandas as pd
    from decimal import Decimal

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    df = pd.read_csv(forecast_csv)
    count = 0

    with table.batch_writer() as batch:
        for _, row in df.iterrows():
            item = {}
            for col in df.columns:
                val = row[col]
                if pd.isna(val):
                    continue
                # DynamoDB doesn't accept float — use Decimal
                if isinstance(val, float):
                    item[col] = Decimal(str(round(val, 4)))
                elif isinstance(val, (int,)):
                    item[col] = int(val)
                else:
                    item[col] = str(val)

            # Composite key: branch#scenario#period
            item["pk"] = f"{row['branch']}#{row['scenario']}"
            item["sk"] = f"period#{int(row['forecast_period'])}"

            batch.put_item(Item=item)
            count += 1

    return count


# ── resolve event parameters ─────────────────────────────────────────────

def _parse_event(event: dict) -> dict:
    """Extract config from event payload or env vars."""

    # If coming from Step Functions, it may carry the ETL output
    etl_output = event.get("etl_result", {})

    bucket = (
        event.get("s3_bucket")
        or etl_output.get("s3_bucket")
        or os.environ.get("S3_BUCKET", "")
    )
    processed_prefix = (
        event.get("s3_processed_prefix")
        or os.environ.get("S3_PROCESSED_PREFIX", "processed/")
    )
    results_prefix = (
        event.get("s3_results_prefix")
        or os.environ.get("S3_RESULTS_PREFIX", "results/forecast/")
    )
    dynamodb_table = (
        event.get("dynamodb_table")
        or os.environ.get("DYNAMODB_TABLE", "")
    )

    return {
        "bucket": bucket,
        "processed_prefix": processed_prefix,
        "results_prefix": results_prefix,
        "dynamodb_table": dynamodb_table,
    }


# ── Lambda handler ───────────────────────────────────────────────────────

def handler(event: dict, context: Any = None) -> dict:
    """
    AWS Lambda entry-point for demand forecasting.

    Returns
    -------
    dict  with keys: status, total_rows, output_s3_keys, dynamodb_items
    """
    logger.info("Forecast handler invoked.  Event keys: %s", list(event.keys()))

    cfg = _parse_event(event)
    bucket = cfg["bucket"]

    if not bucket:
        return {
            "status": "error",
            "message": "No S3 bucket provided (event or S3_BUCKET env var).",
        }

    with tempfile.TemporaryDirectory(prefix="conut_forecast_") as tmpdir:
        tmp = Path(tmpdir)
        processed_dir = tmp / "processed"
        processed_dir.mkdir()
        output_dir = tmp / "forecast_output"
        output_dir.mkdir()
        by_branch_dir = output_dir / "demand_forecast_by_branch"
        by_branch_dir.mkdir()

        # 1. Download the 3 CSVs the forecast needs
        logger.info("Downloading processed CSVs from s3://%s/%s …",
                     bucket, cfg["processed_prefix"])
        downloaded = _download_processed(bucket, cfg["processed_prefix"], processed_dir)
        logger.info("Downloaded %d files.", len(downloaded))

        # 2. Patch the forecast's input path to read from our temp dir
        from pipelines.demand_forecast import prepare, run_forecast

        original_output_dir = prepare._OUTPUT_DIR
        prepare._OUTPUT_DIR = processed_dir

        original_forecast_output = run_forecast.OUTPUT_DIR
        original_forecast_by_branch = run_forecast.BY_BRANCH_DIR
        run_forecast.OUTPUT_DIR = output_dir
        run_forecast.BY_BRANCH_DIR = by_branch_dir

        try:
            df = run_forecast.run()
        finally:
            prepare._OUTPUT_DIR = original_output_dir
            run_forecast.OUTPUT_DIR = original_forecast_output
            run_forecast.BY_BRANCH_DIR = original_forecast_by_branch

        total_rows = len(df)
        logger.info("Forecast produced %d rows.", total_rows)

        # 3. Upload results to S3
        logger.info("Uploading results to s3://%s/%s …",
                     bucket, cfg["results_prefix"])
        uploaded = _upload_results(output_dir, bucket, cfg["results_prefix"])

        # 4. Optionally write to DynamoDB for agent querying
        dynamo_count = 0
        if cfg["dynamodb_table"]:
            all_csv = output_dir / "demand_forecast_all.csv"
            if all_csv.exists():
                logger.info("Writing to DynamoDB table %s …", cfg["dynamodb_table"])
                dynamo_count = _write_to_dynamodb(cfg["dynamodb_table"], all_csv)
                logger.info("Wrote %d items to DynamoDB.", dynamo_count)

    return {
        "status": "success",
        "total_rows": total_rows,
        "output_s3_keys": uploaded,
        "output_s3_prefix": f"s3://{bucket}/{cfg['results_prefix']}",
        "dynamodb_items_written": dynamo_count,
    }


# ── local invocation ─────────────────────────────────────────────────────

def run_local() -> dict:
    """
    Run the forecast pipeline locally (no S3/DynamoDB).
    Uses existing CSVs in ``pipelines/output/``.

    Returns
    -------
    dict  with keys: status, total_rows, output_dir
    """
    from pipelines.demand_forecast.run_forecast import run as forecast_run

    df = forecast_run()
    output_dir = str(PROJECT_ROOT / "pipelines" / "demand_forecast" / "output")
    return {
        "status": "success",
        "total_rows": len(df),
        "output_dir": output_dir,
    }


if __name__ == "__main__":
    result = run_local()
    print(json.dumps(result, indent=2))
