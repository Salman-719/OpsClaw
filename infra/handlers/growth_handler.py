"""
Growth-Strategy Lambda Handler
================================
AWS Lambda entry-point that wraps Feature 5 (coffee & milkshake growth strategy).

Trigger: Step Functions (after ETL stage completes).

Event schema:
  {
    "s3_bucket": "conut-data-<env>",
    "s3_processed_prefix": "processed/",
    "s3_results_prefix": "results/growth/",
    "dynamodb_table": "conut-growth-results-<env>"
  }

Environment variables (set in CDK):
  S3_BUCKET, S3_PROCESSED_PREFIX, S3_RESULTS_PREFIX, DYNAMODB_GROWTH_TABLE
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
    """Download ETL output CSVs that the growth pipeline needs."""
    s3 = _s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    needed = {"feat_branch_item.csv", "transaction_baskets_basket_core.csv"}
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

def _add_beverage_kpi_explanations(kpi_df) -> None:
    """Add an 'explanation' column to branch_beverage_kpis DataFrame."""
    explanations = []
    for _, row in kpi_df.iterrows():
        branch = row["branch"]
        total_orders = int(row["total_orders"])
        bev_orders = int(row["beverage_orders"])
        attach_rate = row["beverage_attachment_rate"]
        best_rate = row["best_branch_rate"]
        gap = row["beverage_gap_to_best"]
        bev_rev_share = row.get("bev_revenue_share", 0)

        if attach_rate >= best_rate:
            perf = "the benchmark leader"
        elif gap < 0.05:
            perf = "close to the best performer"
        elif gap < 0.10:
            perf = "moderately below the best performer"
        else:
            perf = "significantly below the best performer"

        explanation = (
            f"{branch} has a beverage attachment rate of {attach_rate:.1%} "
            f"({bev_orders}/{total_orders} orders include beverages). "
            f"This is {perf} ({best_rate:.1%}), with a gap of {gap:.1%}. "
            f"Beverage revenue share: {bev_rev_share:.1%}."
        )
        explanations.append(explanation)
    kpi_df["explanation"] = explanations


def _add_growth_potential_explanations(growth_df) -> None:
    """Add an 'explanation' column to branch_growth_potential DataFrame."""
    explanations = []
    for _, row in growth_df.iterrows():
        branch = row["branch"]
        score = row["potential_score"]
        rank = int(row["potential_rank"])
        attach_rate = row["beverage_attachment_rate"]
        gap = row["beverage_gap_to_best"]
        top_bundle = row.get("top_bundle_rule", "N/A")
        avg_lift = row.get("avg_lift", 0)

        if score >= 0.7:
            priority = "high-priority"
        elif score >= 0.3:
            priority = "medium-priority"
        else:
            priority = "low-priority"

        explanation = (
            f"{branch} is ranked #{rank} for beverage growth potential "
            f"(score={score:.3f}, {priority}). "
            f"Current attachment rate: {attach_rate:.1%}, gap to best: {gap:.1%}. "
            f"Average association lift: {avg_lift:.1f}. "
            f"Top recommended bundle: {top_bundle}."
        )
        explanations.append(explanation)
    growth_df["explanation"] = explanations


def _add_assoc_rules_explanations(rules_df) -> None:
    """Add an 'explanation' column to assoc_rules_by_branch DataFrame."""
    explanations = []
    for _, row in rules_df.iterrows():
        branch = row["branch"]
        ant = row["antecedents"]
        cons = row["consequents"]
        support = row["support"]
        confidence = row["confidence"]
        lift = row["lift"]

        if lift >= 10:
            strength = "very strong"
        elif lift >= 3:
            strength = "strong"
        elif lift >= 1.5:
            strength = "moderate"
        else:
            strength = "weak"

        explanation = (
            f"At {branch}, customers who buy {ant} are {lift:.1f}x more likely "
            f"to also buy {cons} ({strength} association). "
            f"This pair appears in {support:.1%} of orders with {confidence:.0%} confidence."
        )
        explanations.append(explanation)
    rules_df["explanation"] = explanations


# ── DynamoDB writers ─────────────────────────────────────────────────────

def _write_growth_to_dynamodb(table_name: str, growth_df) -> int:
    """
    Write branch growth potential rows to DynamoDB.
    Key: pk = branch, sk = "growth_potential"
    """
    import boto3
    import pandas as pd

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    count = 0

    with table.batch_writer() as batch:
        for _, row in growth_df.iterrows():
            item = {"pk": str(row["branch"]), "sk": "growth_potential", "record_type": "growth_potential"}
            for col in growth_df.columns:
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


def _write_kpis_to_dynamodb(table_name: str, kpi_df) -> int:
    """
    Write beverage KPI rows to DynamoDB.
    Key: pk = branch, sk = "beverage_kpi"
    """
    import boto3
    import pandas as pd

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    count = 0

    with table.batch_writer() as batch:
        for _, row in kpi_df.iterrows():
            item = {"pk": str(row["branch"]), "sk": "beverage_kpi", "record_type": "beverage_kpi"}
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


def _write_rules_to_dynamodb(table_name: str, rules_df) -> int:
    """
    Write association rules to DynamoDB.
    Key: pk = branch, sk = "rule#<antecedent>#<consequent>"
    """
    import boto3
    import pandas as pd

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    count = 0

    with table.batch_writer() as batch:
        for _, row in rules_df.iterrows():
            ant = str(row["antecedents"]).replace("#", "_")
            cons = str(row["consequents"]).replace("#", "_")
            item = {
                "pk": str(row["branch"]),
                "sk": f"rule#{ant}#{cons}",
                "record_type": "association_rule",
                "branch": str(row["branch"]),
                "antecedents": str(row["antecedents"]),
                "consequents": str(row["consequents"]),
                "support": Decimal(str(round(float(row["support"]), 6))),
                "confidence": Decimal(str(round(float(row["confidence"]), 6))),
                "lift": Decimal(str(round(float(row["lift"]), 4))),
                "explanation": str(row.get("explanation", "")),
            }
            batch.put_item(Item=item)
            count += 1
    return count


def _write_recommendation_to_dynamodb(table_name: str, rec: dict) -> int:
    """
    Write the growth recommendation as a single DynamoDB item.
    Key: pk = "recommendation", sk = "growth"
    """
    import boto3

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    branch_actions = rec.get("branch_actions", [])
    explanation = (
        f"Strategy: {rec.get('strategy', 'N/A')}. "
        f"Objective: {rec.get('objective', 'N/A')}. "
        f"Key findings: {'; '.join(rec.get('key_findings', []))}. "
        f"Top action: {branch_actions[0]['action'] if branch_actions else 'N/A'} "
        f"at {branch_actions[0]['branch'] if branch_actions else 'N/A'}."
    )

    item = {
        "pk": "recommendation",
        "sk": "growth",
        "record_type": "recommendation",
        "strategy": str(rec.get("strategy", "")),
        "objective": str(rec.get("objective", "")),
        "key_findings": json.dumps(rec.get("key_findings", [])),
        "branch_actions": json.dumps(rec.get("branch_actions", [])),
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
    processed_prefix = (
        event.get("s3_processed_prefix")
        or os.environ.get("S3_PROCESSED_PREFIX", "processed/")
    )
    results_prefix = (
        event.get("s3_results_prefix")
        or os.environ.get("S3_RESULTS_PREFIX", "results/growth/")
    )
    dynamodb_table = (
        event.get("dynamodb_table")
        or os.environ.get("DYNAMODB_GROWTH_TABLE", "")
    )
    return {
        "bucket": bucket,
        "processed_prefix": processed_prefix,
        "results_prefix": results_prefix,
        "dynamodb_table": dynamodb_table,
    }


# ── Lambda handler ───────────────────────────────────────────────────────

def handler(event: dict, context: Any = None) -> dict:
    """AWS Lambda entry-point for growth strategy analysis."""
    logger.info("Growth handler invoked.  Event keys: %s", list(event.keys()))

    cfg = _parse_event(event)
    bucket = cfg["bucket"]

    if not bucket:
        return {
            "status": "error",
            "message": "No S3 bucket provided (event or S3_BUCKET env var).",
        }

    with tempfile.TemporaryDirectory(prefix="conut_growth_") as tmpdir:
        tmp = Path(tmpdir)
        processed_dir = tmp / "processed"
        processed_dir.mkdir()
        output_dir = tmp / "growth_output"
        output_dir.mkdir()

        # 1. Download ETL output from S3
        logger.info("Downloading processed CSVs from s3://%s/%s …", bucket, cfg["processed_prefix"])
        downloaded = _download_processed(bucket, cfg["processed_prefix"], processed_dir)
        if not downloaded:
            return {
                "status": "error",
                "message": f"Required CSVs not found in s3://{bucket}/{cfg['processed_prefix']}",
            }
        logger.info("Downloaded %d processed CSV files.", len(downloaded))

        # 2. Run growth strategy pipeline
        from analytics.growth.run import run_pipeline

        run_pipeline(data_dir=str(processed_dir), out_dir=str(output_dir))

        # 3. Read outputs and add explanations
        import pandas as pd

        kpi_path = output_dir / "branch_beverage_kpis.csv"
        growth_path = output_dir / "branch_growth_potential.csv"
        rules_path = output_dir / "assoc_rules_by_branch.csv"
        rec_path = output_dir / "recommendation.json"

        kpi_df = pd.read_csv(kpi_path) if kpi_path.exists() else None
        growth_df = pd.read_csv(growth_path) if growth_path.exists() else None
        rules_df = pd.read_csv(rules_path) if rules_path.exists() else None
        recommendation = json.loads(rec_path.read_text()) if rec_path.exists() else {}

        kpi_count = 0
        growth_count = 0
        rules_count = 0

        if kpi_df is not None and len(kpi_df) > 0:
            _add_beverage_kpi_explanations(kpi_df)
            kpi_df.to_csv(kpi_path, index=False)
            kpi_count = len(kpi_df)

        if growth_df is not None and len(growth_df) > 0:
            _add_growth_potential_explanations(growth_df)
            growth_df.to_csv(growth_path, index=False)
            growth_count = len(growth_df)

        if rules_df is not None and len(rules_df) > 0:
            _add_assoc_rules_explanations(rules_df)
            rules_df.to_csv(rules_path, index=False)
            rules_count = len(rules_df)

        logger.info("Added explanations: %d KPIs, %d growth rows, %d rules.",
                     kpi_count, growth_count, rules_count)

        # Count output files
        output_files = sorted(f.name for f in output_dir.iterdir() if f.is_file())

        # 4. Upload to S3
        logger.info("Uploading results to s3://%s/%s …", bucket, cfg["results_prefix"])
        uploaded = _upload_results(output_dir, bucket, cfg["results_prefix"])

        # 5. Write to DynamoDB
        dynamo_count = 0
        if cfg["dynamodb_table"]:
            logger.info("Writing to DynamoDB table %s …", cfg["dynamodb_table"])
            if kpi_df is not None and len(kpi_df) > 0:
                dynamo_count += _write_kpis_to_dynamodb(cfg["dynamodb_table"], kpi_df)
            if growth_df is not None and len(growth_df) > 0:
                dynamo_count += _write_growth_to_dynamodb(cfg["dynamodb_table"], growth_df)
            if rules_df is not None and len(rules_df) > 0:
                dynamo_count += _write_rules_to_dynamodb(cfg["dynamodb_table"], rules_df)
            if recommendation:
                dynamo_count += _write_recommendation_to_dynamodb(
                    cfg["dynamodb_table"], recommendation
                )
            logger.info("Wrote %d items to DynamoDB.", dynamo_count)

    return {
        "status": "success",
        "kpi_rows": kpi_count,
        "growth_rows": growth_count,
        "rules_rows": rules_count,
        "output_files": output_files,
        "output_s3_keys": uploaded,
        "output_s3_prefix": f"s3://{bucket}/{cfg['results_prefix']}",
        "dynamodb_items_written": dynamo_count,
    }


# ── local invocation ─────────────────────────────────────────────────────

def run_local() -> dict:
    """
    Run growth strategy locally (no S3/DynamoDB).
    Uses existing ETL output from pipelines/output/.
    """
    import pandas as pd

    data_dir = PROJECT_ROOT / "pipelines" / "output"
    output_dir = PROJECT_ROOT / "analytics" / "growth" / "output"

    if not data_dir.exists():
        return {"status": "error", "message": f"Data dir not found: {data_dir}"}

    from analytics.growth.run import run_pipeline

    run_pipeline(data_dir=str(data_dir), out_dir=str(output_dir))

    # Read outputs and add explanations
    kpi_path = output_dir / "branch_beverage_kpis.csv"
    growth_path = output_dir / "branch_growth_potential.csv"
    rules_path = output_dir / "assoc_rules_by_branch.csv"
    rec_path = output_dir / "recommendation.json"

    kpi_df = pd.read_csv(kpi_path) if kpi_path.exists() else None
    growth_df = pd.read_csv(growth_path) if growth_path.exists() else None
    rules_df = pd.read_csv(rules_path) if rules_path.exists() else None
    recommendation = json.loads(rec_path.read_text()) if rec_path.exists() else {}

    if kpi_df is not None and len(kpi_df) > 0:
        _add_beverage_kpi_explanations(kpi_df)
        kpi_df.to_csv(kpi_path, index=False)

    if growth_df is not None and len(growth_df) > 0:
        _add_growth_potential_explanations(growth_df)
        growth_df.to_csv(growth_path, index=False)

    if rules_df is not None and len(rules_df) > 0:
        _add_assoc_rules_explanations(rules_df)
        rules_df.to_csv(rules_path, index=False)

    return {
        "status": "success",
        "kpi_rows": len(kpi_df) if kpi_df is not None else 0,
        "growth_rows": len(growth_df) if growth_df is not None else 0,
        "rules_rows": len(rules_df) if rules_df is not None else 0,
        "output_files": sorted(f.name for f in output_dir.iterdir() if f.is_file()),
        "output_dir": str(output_dir),
        "recommendation_strategy": recommendation.get("strategy", "N/A"),
    }


if __name__ == "__main__":
    result = run_local()
    print(json.dumps(result, indent=2, default=str))
