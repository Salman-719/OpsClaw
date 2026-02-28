"""
Expansion-Feasibility Lambda Handler
======================================
AWS Lambda entry-point that wraps Feature 3 (branch expansion feasibility).

Trigger: Step Functions (after ETL stage completes).

Event schema:
  {
    "s3_bucket": "conut-data-<env>",
    "s3_input_prefix": "input/",
    "s3_results_prefix": "results/expansion/",
    "dynamodb_table": "conut-expansion-results-<env>"
  }

Environment variables (set in CDK):
  S3_BUCKET, S3_INPUT_PREFIX, S3_RESULTS_PREFIX, DYNAMODB_EXPANSION_TABLE
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


def _download_raw_csvs(bucket: str, prefix: str, local_dir: Path) -> list[Path]:
    """Download all raw CSVs from the S3 input/ prefix (before ETL)."""
    s3 = _s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    downloaded: list[Path] = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            fname = Path(key).name
            if fname.lower().endswith(".csv"):
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

def _add_kpi_explanations(kpi_df) -> None:
    """Add an 'explanation' column to branch_kpis DataFrame."""
    explanations = []
    for _, row in kpi_df.iterrows():
        branch = row["branch"]
        revenue = row["avg_monthly_revenue"]
        growth = row["recent_growth_rate"]
        volatility = row["revenue_volatility"]
        n_months = int(row["n_months"])
        partial = row.get("is_partial_history", False)

        # Growth interpretation
        if growth > 2.0:
            growth_label = "rapidly growing"
        elif growth > 0.5:
            growth_label = "growing steadily"
        elif growth > 0:
            growth_label = "growing slowly"
        elif growth > -0.5:
            growth_label = "roughly flat"
        else:
            growth_label = "declining"

        # Volatility interpretation
        if volatility > 0.8:
            vol_label = "highly volatile"
        elif volatility > 0.4:
            vol_label = "moderately volatile"
        else:
            vol_label = "stable"

        # Data caveat
        caveat = ""
        if partial or n_months < 6:
            caveat = f" Note: only {n_months} months of data — treat as indicative."

        delivery_share = row.get("delivery_share", 0) or 0
        delivery_pct = f"{delivery_share:.1%}" if delivery_share else "negligible"

        explanation = (
            f"{branch} averages {revenue:,.0f} LBP/month in revenue and is "
            f"{growth_label} (growth rate {growth:.2f}). "
            f"Revenue is {vol_label} (volatility={volatility:.2f}). "
            f"Delivery share is {delivery_pct}."
            f"{caveat}"
        )
        explanations.append(explanation)
    kpi_df["explanation"] = explanations


def _add_feasibility_explanations(scores_df) -> None:
    """Add an 'explanation' column to feasibility_scores DataFrame."""
    explanations = []
    for _, row in scores_df.iterrows():
        branch = row["branch"]
        score = row["feasibility_score"]
        tier = row["score_tier"]
        drivers = row.get("top_drivers", "")
        growth = row.get("recent_growth_rate", 0)
        revenue = row.get("avg_monthly_revenue", 0)

        if tier == "High":
            outlook = "highly feasible for expansion"
        elif tier == "Medium":
            outlook = "moderately feasible for expansion"
        else:
            outlook = "not recommended for near-term expansion"

        explanation = (
            f"{branch} region is {outlook} (score={score:.4f}, tier={tier}). "
            f"Average monthly revenue is {revenue:,.0f} LBP with growth rate "
            f"{growth:.2f}. Top drivers: {drivers}."
        )
        explanations.append(explanation)
    scores_df["explanation"] = explanations


# ── DynamoDB writers ─────────────────────────────────────────────────────

def _write_kpis_to_dynamodb(table_name: str, kpi_df) -> int:
    """
    Write branch KPI rows to DynamoDB.
    Key: pk = branch, sk = "kpi"
    """
    import boto3
    import pandas as pd

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    count = 0

    with table.batch_writer() as batch:
        for _, row in kpi_df.iterrows():
            item = {"pk": str(row["branch"]), "sk": "kpi", "record_type": "branch_kpi"}
            for col in kpi_df.columns:
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


def _write_scores_to_dynamodb(table_name: str, scores_df) -> int:
    """
    Write feasibility score rows to DynamoDB.
    Key: pk = branch, sk = "feasibility"
    """
    import boto3
    import pandas as pd

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    count = 0

    with table.batch_writer() as batch:
        for _, row in scores_df.iterrows():
            item = {"pk": str(row["branch"]), "sk": "feasibility", "record_type": "feasibility_score"}
            for col in scores_df.columns:
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


def _write_recommendation_to_dynamodb(table_name: str, recommendation: dict) -> int:
    """
    Write the expansion recommendation as a single DynamoDB item.
    Key: pk = "recommendation", sk = "expansion"
    """
    import boto3

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    # Build explanation from recommendation
    rec = recommendation
    explanation = (
        f"Recommended expansion region: {rec.get('recommended_region', 'N/A')}. "
        f"Best branch to replicate: {rec.get('best_branch_to_replicate', 'N/A')} "
        f"(tier={rec.get('feasibility_tier', 'N/A')}, "
        f"overall score={rec.get('overall_feasibility', 0):.4f}). "
        f"Candidate locations: {', '.join(rec.get('candidate_locations', []))}."
    )

    item = {
        "pk": "recommendation",
        "sk": "expansion",
        "record_type": "recommendation",
        "recommended_region": str(rec.get("recommended_region", "")),
        "candidate_locations": ", ".join(rec.get("candidate_locations", [])),
        "best_branch_to_replicate": str(rec.get("best_branch_to_replicate", "")),
        "feasibility_tier": str(rec.get("feasibility_tier", "")),
        "overall_feasibility": Decimal(str(round(rec.get("overall_feasibility", 0), 4))),
        "region_scores": json.dumps(rec.get("region_scores", {})),
        "growth_summary": json.dumps(rec.get("growth_summary", {})),
        "explanation": explanation,
    }
    table.put_item(Item=item)
    return 1


# ── resolve event parameters ─────────────────────────────────────────────

def _parse_event(event: dict) -> dict:
    etl_output = event.get("etl_result", {})
    bucket = (
        event.get("s3_bucket")
        or etl_output.get("s3_bucket")
        or os.environ.get("S3_BUCKET", "")
    )
    input_prefix = (
        event.get("s3_input_prefix")
        or os.environ.get("S3_INPUT_PREFIX", "input/")
    )
    results_prefix = (
        event.get("s3_results_prefix")
        or os.environ.get("S3_RESULTS_PREFIX", "results/expansion/")
    )
    dynamodb_table = (
        event.get("dynamodb_table")
        or os.environ.get("DYNAMODB_EXPANSION_TABLE", "")
    )
    return {
        "bucket": bucket,
        "input_prefix": input_prefix,
        "results_prefix": results_prefix,
        "dynamodb_table": dynamodb_table,
    }


# ── Lambda handler ───────────────────────────────────────────────────────

def handler(event: dict, context: Any = None) -> dict:
    """AWS Lambda entry-point for expansion feasibility analysis."""
    logger.info("Expansion handler invoked.  Event keys: %s", list(event.keys()))

    cfg = _parse_event(event)
    bucket = cfg["bucket"]

    if not bucket:
        return {
            "status": "error",
            "message": "No S3 bucket provided (event or S3_BUCKET env var).",
        }

    with tempfile.TemporaryDirectory(prefix="conut_expansion_") as tmpdir:
        tmp = Path(tmpdir)
        raw_dir = tmp / "raw"
        raw_dir.mkdir()
        output_dir = tmp / "expansion_output"
        output_dir.mkdir()

        # 1. Download raw CSVs from S3 input/ prefix
        logger.info("Downloading raw CSVs from s3://%s/%s …", bucket, cfg["input_prefix"])
        downloaded = _download_raw_csvs(bucket, cfg["input_prefix"], raw_dir)
        if not downloaded:
            return {
                "status": "error",
                "message": f"No CSV files found in s3://{bucket}/{cfg['input_prefix']}",
            }
        logger.info("Downloaded %d raw CSV files.", len(downloaded))

        # 2. Run expansion feasibility pipeline
        from analytics.expansion.run import run_pipeline

        result = run_pipeline(data_dir=str(raw_dir), out_dir=str(output_dir))

        kpi_df = result["branch_kpis"]
        scores_df = result["feasibility_scores"]
        recommendation = result["recommendation"]

        # 3. Add explanations
        _add_kpi_explanations(kpi_df)
        _add_feasibility_explanations(scores_df)
        logger.info("Added explanations to %d KPI rows and %d score rows.",
                     len(kpi_df), len(scores_df))

        # 4. Save explained CSVs (overwrite originals)
        kpi_df.to_csv(output_dir / "branch_kpis.csv", index=False)
        scores_df.to_csv(output_dir / "feasibility_scores.csv", index=False)

        total_kpi_rows = len(kpi_df)
        total_score_rows = len(scores_df)

        # 5. Upload to S3
        logger.info("Uploading results to s3://%s/%s …", bucket, cfg["results_prefix"])
        uploaded = _upload_results(output_dir, bucket, cfg["results_prefix"])

        # 6. Write to DynamoDB
        dynamo_count = 0
        if cfg["dynamodb_table"]:
            logger.info("Writing to DynamoDB table %s …", cfg["dynamodb_table"])
            dynamo_count += _write_kpis_to_dynamodb(cfg["dynamodb_table"], kpi_df)
            dynamo_count += _write_scores_to_dynamodb(cfg["dynamodb_table"], scores_df)
            dynamo_count += _write_recommendation_to_dynamodb(
                cfg["dynamodb_table"], recommendation
            )
            logger.info("Wrote %d items to DynamoDB.", dynamo_count)

    return {
        "status": "success",
        "total_kpi_rows": total_kpi_rows,
        "total_score_rows": total_score_rows,
        "output_s3_keys": uploaded,
        "output_s3_prefix": f"s3://{bucket}/{cfg['results_prefix']}",
        "dynamodb_items_written": dynamo_count,
    }


# ── local invocation ─────────────────────────────────────────────────────

def run_local() -> dict:
    """
    Run expansion feasibility locally (no S3/DynamoDB).
    Uses existing raw CSVs in conut_bakery_scaled_data/.
    """
    data_dir = PROJECT_ROOT / "conut_bakery_scaled_data"
    output_dir = PROJECT_ROOT / "analytics" / "expansion" / "output"

    if not data_dir.exists():
        return {"status": "error", "message": f"Data dir not found: {data_dir}"}

    from analytics.expansion.run import run_pipeline

    result = run_pipeline(data_dir=str(data_dir), out_dir=str(output_dir))

    kpi_df = result["branch_kpis"]
    scores_df = result["feasibility_scores"]
    recommendation = result["recommendation"]

    # Add explanations
    _add_kpi_explanations(kpi_df)
    _add_feasibility_explanations(scores_df)

    # Save explained CSVs
    kpi_df.to_csv(output_dir / "branch_kpis.csv", index=False)
    scores_df.to_csv(output_dir / "feasibility_scores.csv", index=False)

    return {
        "status": "success",
        "total_kpi_rows": len(kpi_df),
        "total_score_rows": len(scores_df),
        "branches": sorted(kpi_df["branch"].tolist()),
        "output_dir": str(output_dir),
        "recommendation_region": recommendation.get("recommended_region", "N/A"),
    }


if __name__ == "__main__":
    result = run_local()
    print(json.dumps(result, indent=2, default=str))
