"""
Staffing-Estimation Lambda Handler
====================================
AWS Lambda entry-point that wraps Feature 4 (shift staffing estimation).

Trigger: Step Functions (after ETL stage completes).

Event schema:
  {
    "s3_bucket": "conut-data-<env>",
    "s3_processed_prefix": "processed/",
    "s3_results_prefix": "results/staffing/",
    "dynamodb_table": "conut-staffing-results-<env>"
  }

Environment variables (set in CDK):
  S3_BUCKET, S3_PROCESSED_PREFIX, S3_RESULTS_PREFIX, DYNAMODB_STAFFING_TABLE
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from decimal import Decimal
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
    """Download ETL output CSVs that the staffing pipeline needs."""
    s3 = _s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    needed = {
        "time_and_attendance_logs.csv",
        "customer_orders_delivery.csv",
        "average_sales_by_menu.csv",
        "monthly_sales_by_branch.csv",
    }
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
    """Upload all files in local_dir to S3."""
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


# ── Explainability builders ──────────────────────────────────────────────

def _add_findings_explanations(findings_df) -> None:
    """
    Add an 'explanation' column to branch_staffing_findings DataFrame.
    Each row gets a human-readable summary of the staffing situation.
    """
    explanations = []
    for _, row in findings_df.iterrows():
        branch = row["branch"]
        confidence = row.get("demand_confidence", "unknown")
        total_slots = int(row.get("analysis_slots", 0))
        under = int(row.get("understaffed_slots", 0))
        balanced = int(row.get("balanced_slots", 0))
        over = int(row.get("overstaffed_slots", 0))
        avg_active = row.get("avg_active_employees_across_slots", 0)
        avg_required = row.get("avg_required_employees_base", 0)
        worst_under_slot = row.get("worst_understaffed_slot", "N/A")
        worst_under_gap = row.get("worst_understaffed_gap", 0)
        worst_over_slot = row.get("worst_overstaffed_slot", "N/A")
        worst_over_gap = row.get("worst_overstaffed_gap", 0)

        # Overall status
        if under > over * 2:
            status = "significantly understaffed overall"
        elif under > over:
            status = "somewhat understaffed overall"
        elif over > under * 2:
            status = "significantly overstaffed overall"
        elif over > under:
            status = "somewhat overstaffed overall"
        else:
            status = "roughly balanced"

        explanation = (
            f"{branch} is {status}. Across {total_slots} time slots: "
            f"{under} understaffed, {balanced} balanced, {over} overstaffed. "
            f"Average active employees: {avg_active:.1f}, average required: {avg_required:.1f}. "
            f"Worst understaffed slot: {worst_under_slot} (gap={worst_under_gap}). "
            f"Worst overstaffed slot: {worst_over_slot} (gap={worst_over_gap}). "
            f"Demand confidence: {confidence}."
        )
        explanations.append(explanation)
    findings_df["explanation"] = explanations


def _add_gap_explanations(gap_df) -> None:
    """
    Add an 'explanation' column to staffing_gap_hourly DataFrame.
    Each row gets a concise explanation of the staffing gap for that slot.
    """
    explanations = []
    for _, row in gap_df.iterrows():
        branch = row["branch"]
        day = row["day_of_week"]
        hour = int(row["hour"])
        active = row.get("avg_active_employees", 0)
        required = row.get("required_employees_base", 0)
        gap = row.get("gap_base", 0)
        status = row.get("status", "unknown")
        delivery_est = row.get("delivery_orders_est", 0)
        total_est = row.get("total_orders_est_base", 0)

        if status == "understaffed":
            action = f"Need {abs(gap):.1f} more employees"
        elif status == "overstaffed":
            action = f"Could reduce by {abs(gap):.1f} employees"
        else:
            action = "Staffing level is appropriate"

        explanation = (
            f"{branch} on {day} at {hour:02d}:00 — {status}. "
            f"Active: {active:.1f}, required: {required:.1f} (gap={gap:+.1f}). "
            f"Estimated orders: {total_est:.1f} total, {delivery_est:.1f} delivery. "
            f"{action}."
        )
        explanations.append(explanation)
    gap_df["explanation"] = explanations


# ── DynamoDB writers ─────────────────────────────────────────────────────

def _write_findings_to_dynamodb(table_name: str, findings_df) -> int:
    """
    Write branch staffing findings to DynamoDB.
    Key: pk = branch, sk = "findings"
    """
    import boto3
    import pandas as pd

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    count = 0

    with table.batch_writer() as batch:
        for _, row in findings_df.iterrows():
            item = {"pk": str(row["branch"]), "sk": "findings", "record_type": "staffing_findings"}
            for col in findings_df.columns:
                val = row[col]
                if pd.isna(val):
                    continue
                if isinstance(val, float):
                    item[col] = Decimal(str(round(val, 6)))
                elif isinstance(val, (int,)):
                    item[col] = int(val)
                else:
                    item[col] = str(val)
            batch.put_item(Item=item)
            count += 1
    return count


def _write_gaps_to_dynamodb(table_name: str, gap_df) -> int:
    """
    Write hourly staffing gap rows to DynamoDB.
    Key: pk = branch, sk = "gap#<day>#<hour>"
    """
    import boto3
    import pandas as pd

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    count = 0

    # Only write non-balanced slots to keep DynamoDB lean
    interesting = gap_df[gap_df["status"] != "balanced"] if "status" in gap_df.columns else gap_df

    cols_to_write = [
        "branch", "day_of_week", "hour", "avg_active_employees",
        "required_employees_base", "gap_base", "status",
        "delivery_orders_est", "total_orders_est_base", "explanation",
    ]
    cols_to_write = [c for c in cols_to_write if c in gap_df.columns]

    with table.batch_writer() as batch:
        for _, row in interesting.iterrows():
            item = {
                "pk": str(row["branch"]),
                "sk": f"gap#{row['day_of_week']}#{int(row['hour']):02d}",
                "record_type": "staffing_gap",
            }
            for col in cols_to_write:
                val = row[col]
                if pd.isna(val):
                    continue
                if isinstance(val, float):
                    item[col] = Decimal(str(round(val, 4)))
                elif isinstance(val, (int,)):
                    item[col] = int(val)
                else:
                    item[col] = str(val)
            batch.put_item(Item=item)
            count += 1
    return count


# ── resolve event parameters ─────────────────────────────────────────────

def _parse_event(event: dict) -> dict:
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
        or os.environ.get("S3_RESULTS_PREFIX", "results/staffing/")
    )
    dynamodb_table = (
        event.get("dynamodb_table")
        or os.environ.get("DYNAMODB_STAFFING_TABLE", "")
    )
    return {
        "bucket": bucket,
        "processed_prefix": processed_prefix,
        "results_prefix": results_prefix,
        "dynamodb_table": dynamodb_table,
    }


# ── Lambda handler ───────────────────────────────────────────────────────

def handler(event: dict, context: Any = None) -> dict:
    """AWS Lambda entry-point for staffing estimation."""
    logger.info("Staffing handler invoked.  Event keys: %s", list(event.keys()))

    cfg = _parse_event(event)
    bucket = cfg["bucket"]

    if not bucket:
        return {
            "status": "error",
            "message": "No S3 bucket provided (event or S3_BUCKET env var).",
        }

    with tempfile.TemporaryDirectory(prefix="conut_staffing_") as tmpdir:
        tmp = Path(tmpdir)
        processed_dir = tmp / "processed"
        processed_dir.mkdir()
        output_dir = tmp / "staffing_output"
        output_dir.mkdir()

        # 1. Download ETL output from S3
        logger.info("Downloading processed CSVs from s3://%s/%s …", bucket, cfg["processed_prefix"])
        downloaded = _download_processed(bucket, cfg["processed_prefix"], processed_dir)
        if not downloaded:
            return {
                "status": "error",
                "message": f"No required CSVs found in s3://{bucket}/{cfg['processed_prefix']}",
            }
        logger.info("Downloaded %d processed CSV files.", len(downloaded))

        # 2. Run staffing estimation pipeline
        from analytics.staffing import run as staffing_run

        result_dfs = staffing_run(
            input_dir=str(processed_dir),
            output_dir=str(output_dir),
            verbose=False,
        )

        # 3. Add explanations to key outputs
        import pandas as pd

        findings_path = output_dir / "branch_staffing_findings.csv"
        gap_path = output_dir / "staffing_gap_hourly.csv"

        findings_df = pd.read_csv(findings_path) if findings_path.exists() else None
        gap_df = pd.read_csv(gap_path) if gap_path.exists() else None

        findings_count = 0
        gap_count = 0

        if findings_df is not None and len(findings_df) > 0:
            _add_findings_explanations(findings_df)
            findings_df.to_csv(findings_path, index=False)
            findings_count = len(findings_df)
            logger.info("Added explanations to %d findings rows.", findings_count)

        if gap_df is not None and len(gap_df) > 0:
            _add_gap_explanations(gap_df)
            gap_df.to_csv(gap_path, index=False)
            gap_count = len(gap_df)
            logger.info("Added explanations to %d gap rows.", gap_count)

        # Count output files
        output_files = sorted(f.name for f in output_dir.iterdir() if f.is_file())

        # 4. Upload to S3
        logger.info("Uploading results to s3://%s/%s …", bucket, cfg["results_prefix"])
        uploaded = _upload_results(output_dir, bucket, cfg["results_prefix"])

        # 5. Write to DynamoDB
        dynamo_count = 0
        if cfg["dynamodb_table"]:
            logger.info("Writing to DynamoDB table %s …", cfg["dynamodb_table"])
            if findings_df is not None and len(findings_df) > 0:
                dynamo_count += _write_findings_to_dynamodb(cfg["dynamodb_table"], findings_df)
            if gap_df is not None and len(gap_df) > 0:
                dynamo_count += _write_gaps_to_dynamodb(cfg["dynamodb_table"], gap_df)
            logger.info("Wrote %d items to DynamoDB.", dynamo_count)

    return {
        "status": "success",
        "findings_rows": findings_count,
        "gap_rows": gap_count,
        "output_files": output_files,
        "output_s3_keys": uploaded,
        "output_s3_prefix": f"s3://{bucket}/{cfg['results_prefix']}",
        "dynamodb_items_written": dynamo_count,
    }


# ── local invocation ─────────────────────────────────────────────────────

def run_local() -> dict:
    """
    Run staffing estimation locally (no S3/DynamoDB).
    Uses existing ETL output from pipelines/output/.
    """
    import pandas as pd

    input_dir = PROJECT_ROOT / "pipelines" / "output"
    output_dir = PROJECT_ROOT / "analytics" / "staffing" / "output"

    if not input_dir.exists():
        return {"status": "error", "message": f"Input dir not found: {input_dir}"}

    from analytics.staffing import run as staffing_run

    result_dfs = staffing_run(
        input_dir=str(input_dir),
        output_dir=str(output_dir),
        verbose=True,
    )

    # Add explanations to key outputs
    findings_path = output_dir / "branch_staffing_findings.csv"
    gap_path = output_dir / "staffing_gap_hourly.csv"

    findings_df = pd.read_csv(findings_path) if findings_path.exists() else None
    gap_df = pd.read_csv(gap_path) if gap_path.exists() else None

    if findings_df is not None and len(findings_df) > 0:
        _add_findings_explanations(findings_df)
        findings_df.to_csv(findings_path, index=False)

    if gap_df is not None and len(gap_df) > 0:
        _add_gap_explanations(gap_df)
        gap_df.to_csv(gap_path, index=False)

    output_files = sorted(f.name for f in output_dir.iterdir() if f.is_file())

    return {
        "status": "success",
        "findings_rows": len(findings_df) if findings_df is not None else 0,
        "gap_rows": len(gap_df) if gap_df is not None else 0,
        "output_files": output_files,
        "output_dir": str(output_dir),
    }


if __name__ == "__main__":
    result = run_local()
    print(json.dumps(result, indent=2, default=str))
