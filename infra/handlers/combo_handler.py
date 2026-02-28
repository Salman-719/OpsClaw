"""
Combo-Optimization Lambda Handler
===================================
AWS Lambda entry-point that wraps Feature 1 (combo_optimization).

Trigger: Step Functions (after ETL stage completes).

Event schema (direct invoke / Step Functions):
  {
    "s3_bucket": "conut-data-<env>",
    "s3_processed_prefix": "processed/",
    "s3_results_prefix": "results/combo/",
    "dynamodb_table": "conut-combo-results-<env>"
  }

Environment variables (set in CDK):
  S3_BUCKET, S3_PROCESSED_PREFIX, S3_RESULTS_PREFIX, DYNAMODB_COMBO_TABLE
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


def _download_file(bucket: str, prefix: str, filename: str, local_dir: Path) -> Path | None:
    """Download a single file from S3. Returns local path or None."""
    s3 = _s3_client()
    key = f"{prefix}{filename}"
    local_path = local_dir / filename
    try:
        s3.download_file(bucket, key, str(local_path))
        logger.info("  ↓ s3://%s/%s → %s", bucket, key, local_path)
        return local_path
    except Exception as e:
        logger.warning("  ✗ Could not download s3://%s/%s: %s", bucket, key, e)
        return None


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


# ── Explainability builder ───────────────────────────────────────────────

def _add_explanations(pairs_df) -> None:
    """
    Add an 'explanation' column to the combo pairs DataFrame.
    Each row gets a human-readable sentence explaining the association.
    """
    import pandas as pd

    explanations = []
    for _, row in pairs_df.iterrows():
        scope = row["scope"]
        item_a = row["item_a"]
        item_b = row["item_b"]
        count_ab = int(row["count_ab"])
        n_orders = int(row["n_orders"])
        support = row["support"]
        conf_ab = row["confidence_ab"]
        conf_ba = row["confidence_ba"]
        lift = row["lift"]

        # Scope context
        if scope == "overall":
            scope_text = "across all branches and channels"
        elif scope.startswith("branch:") and "|" not in scope:
            scope_text = f"at {scope.replace('branch:', '')}"
        elif scope.startswith("channel:"):
            scope_text = f"via {scope.replace('channel:', '').lower()} orders"
        else:
            parts = scope.split("|")
            branch = parts[0].replace("branch:", "")
            channel = parts[1].replace("channel:", "").lower() if len(parts) > 1 else "unknown"
            scope_text = f"at {branch} via {channel} orders"

        # Lift interpretation
        if lift >= 5.0:
            lift_label = "very strong"
        elif lift >= 2.0:
            lift_label = "strong"
        elif lift >= 1.2:
            lift_label = "moderate"
        elif lift >= 1.0:
            lift_label = "weak"
        else:
            lift_label = "negative (bought less together than expected)"

        # Confidence direction
        if conf_ab > conf_ba:
            direction = (
                f"When a customer buys {item_a}, there is a {conf_ab:.0%} chance "
                f"they also buy {item_b}."
            )
        else:
            direction = (
                f"When a customer buys {item_b}, there is a {conf_ba:.0%} chance "
                f"they also buy {item_a}."
            )

        # Data basis warning
        if count_ab < 5:
            caveat = f" Caution: only {count_ab} co-occurrences — treat as indicative only."
        elif count_ab < 10:
            caveat = f" Based on {count_ab} co-occurrences — moderate evidence."
        else:
            caveat = f" Based on {count_ab} co-occurrences out of {n_orders} orders — solid evidence."

        explanation = (
            f"{item_a} + {item_b} show a {lift_label} association (lift={lift:.1f}) "
            f"{scope_text}. "
            f"{support:.1%} of orders in this scope contain both items. "
            f"{direction}"
            f"{caveat}"
        )
        explanations.append(explanation)

    pairs_df["explanation"] = explanations


# ── DynamoDB writer ──────────────────────────────────────────────────────

def _write_to_dynamodb(table_name: str, pairs_df) -> int:
    """
    Write combo pair rows to DynamoDB for agent querying.
    Key: pk = scope, sk = "item_a#item_b"
    """
    import boto3
    import pandas as pd
    from decimal import Decimal

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    count = 0

    with table.batch_writer() as batch:
        for _, row in pairs_df.iterrows():
            item = {
                "pk": str(row["scope"]),
                "sk": f"{row['item_a']}#{row['item_b']}",
                "scope": str(row["scope"]),
                "item_a": str(row["item_a"]),
                "item_b": str(row["item_b"]),
                "n_orders": int(row["n_orders"]),
                "count_a": int(row["count_a"]),
                "count_b": int(row["count_b"]),
                "count_ab": int(row["count_ab"]),
                "support": Decimal(str(round(float(row["support"]), 6))),
                "confidence_ab": Decimal(str(round(float(row["confidence_ab"]), 6))),
                "confidence_ba": Decimal(str(round(float(row["confidence_ba"]), 6))),
                "lift": Decimal(str(round(float(row["lift"]), 4))),
                "explanation": str(row["explanation"]),
            }
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
        or os.environ.get("S3_RESULTS_PREFIX", "results/combo/")
    )
    dynamodb_table = (
        event.get("dynamodb_table")
        or os.environ.get("DYNAMODB_COMBO_TABLE", "")
    )
    return {
        "bucket": bucket,
        "processed_prefix": processed_prefix,
        "results_prefix": results_prefix,
        "dynamodb_table": dynamodb_table,
    }


# ── Lambda handler ───────────────────────────────────────────────────────

def handler(event: dict, context: Any = None) -> dict:
    """AWS Lambda entry-point for combo optimization."""
    logger.info("Combo handler invoked.  Event keys: %s", list(event.keys()))

    cfg = _parse_event(event)
    bucket = cfg["bucket"]

    if not bucket:
        return {
            "status": "error",
            "message": "No S3 bucket provided (event or S3_BUCKET env var).",
        }

    with tempfile.TemporaryDirectory(prefix="conut_combo_") as tmpdir:
        tmp = Path(tmpdir)
        processed_dir = tmp / "processed"
        processed_dir.mkdir()
        output_dir = tmp / "combo_output"
        output_dir.mkdir()

        # 1. Download the input CSV from S3
        logger.info("Downloading input from s3://%s/%s …", bucket, cfg["processed_prefix"])
        input_file = _download_file(
            bucket, cfg["processed_prefix"],
            "transaction_baskets_raw_lines.csv", processed_dir,
        )
        if input_file is None:
            return {
                "status": "error",
                "message": "transaction_baskets_raw_lines.csv not found in processed/ prefix.",
            }

        # 2. Run combo optimization
        from analytics.combo.combo_optimization import run as combo_run

        out_baskets = output_dir / "order_baskets.csv"
        out_pairs = output_dir / "combo_pairs.csv"

        baskets_df, pairs_df = combo_run(
            in_path=str(input_file),
            out_baskets=str(output_dir / "order_baskets.parquet"),
            out_pairs=str(output_dir / "combo_pairs.parquet"),
            min_support=0.01,
            min_count_ab=2,
            validate=True,
        )

        # 3. Add explanations
        _add_explanations(pairs_df)
        logger.info("Added explanations to %d combo pair rows.", len(pairs_df))

        # 4. Save CSV versions (with explanations) for S3
        baskets_df_save = baskets_df.copy()
        for col in baskets_df_save.columns:
            if baskets_df_save[col].apply(lambda x: isinstance(x, (frozenset, set))).any():
                baskets_df_save[col] = baskets_df_save[col].apply(
                    lambda x: ", ".join(sorted(x)) if isinstance(x, (frozenset, set)) else x
                )
        baskets_df_save.to_csv(out_baskets, index=False)
        pairs_df.to_csv(out_pairs, index=False)

        # Also save metadata
        meta = {
            "total_baskets": len(baskets_df),
            "total_pairs": len(pairs_df),
            "scopes": sorted(pairs_df["scope"].unique().tolist()) if len(pairs_df) > 0 else [],
            "branches": sorted(baskets_df["branch"].unique().tolist()),
            "channels": sorted(baskets_df["channel"].unique().tolist()),
            "parameters": {
                "min_support": 0.01,
                "min_count_ab": 2,
            },
        }
        meta_path = output_dir / "combo_metadata.json"
        meta_path.write_text(json.dumps(meta, indent=2))

        total_pairs = len(pairs_df)

        # 5. Upload to S3
        logger.info("Uploading results to s3://%s/%s …", bucket, cfg["results_prefix"])
        uploaded = _upload_results(output_dir, bucket, cfg["results_prefix"])

        # 6. Write to DynamoDB
        dynamo_count = 0
        if cfg["dynamodb_table"] and len(pairs_df) > 0:
            logger.info("Writing to DynamoDB table %s …", cfg["dynamodb_table"])
            dynamo_count = _write_to_dynamodb(cfg["dynamodb_table"], pairs_df)
            logger.info("Wrote %d items to DynamoDB.", dynamo_count)

    return {
        "status": "success",
        "total_baskets": len(baskets_df),
        "total_pairs": total_pairs,
        "output_s3_keys": uploaded,
        "output_s3_prefix": f"s3://{bucket}/{cfg['results_prefix']}",
        "dynamodb_items_written": dynamo_count,
    }


# ── local invocation ─────────────────────────────────────────────────────

def run_local() -> dict:
    """
    Run combo optimization locally (no S3/DynamoDB).
    Uses existing ETL output.
    """
    import pandas as pd

    input_path = PROJECT_ROOT / "pipelines" / "output" / "transaction_baskets_raw_lines.csv"
    output_dir = PROJECT_ROOT / "analytics" / "combo" / "data"

    if not input_path.exists():
        return {"status": "error", "message": f"Input not found: {input_path}"}

    from analytics.combo.combo_optimization import run as combo_run

    baskets_df, pairs_df = combo_run(
        in_path=str(input_path),
        out_baskets=str(output_dir / "processed" / "order_baskets.parquet"),
        out_pairs=str(output_dir / "artifacts" / "combo_pairs.parquet"),
        min_support=0.01,
        min_count_ab=2,
        validate=True,
    )

    # Add explanations
    _add_explanations(pairs_df)

    # Save CSV with explanations alongside the parquet
    csv_out = output_dir / "artifacts" / "combo_pairs_explained.csv"
    pairs_df.to_csv(csv_out, index=False)

    return {
        "status": "success",
        "total_baskets": len(baskets_df),
        "total_pairs": len(pairs_df),
        "output_dir": str(output_dir),
        "explained_csv": str(csv_out),
    }


if __name__ == "__main__":
    result = run_local()
    print(json.dumps(result, indent=2, default=str))
