"""
ETL Lambda Handler
==================
AWS Lambda entry-point that wraps ``pipelines.run_pipeline.run()``.

Trigger modes:
  1. **S3 Event** — fired when raw CSVs land in ``s3://<bucket>/input/``
     The handler downloads every CSV under that prefix, runs the ETL, and
     uploads the 15 clean outputs to ``s3://<bucket>/processed/``.

  2. **Direct invoke** — called by Step Functions or by you locally.
     Event schema:
       {
         "s3_bucket": "conut-data-<env>",
         "s3_input_prefix": "input/",
         "s3_output_prefix": "processed/"
       }

Environment variables (set in SAM template):
  S3_BUCKET            default bucket when not in event
  S3_INPUT_PREFIX      default "input/"
  S3_OUTPUT_PREFIX     default "processed/"
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
    """Lazy boto3 client (avoids import at module level for local testing)."""
    import boto3
    return boto3.client("s3")


def _download_inputs(bucket: str, prefix: str, local_dir: Path) -> list[Path]:
    """Download all CSVs under *prefix* to *local_dir*. Returns local paths."""
    s3 = _s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    downloaded: list[Path] = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.lower().endswith(".csv"):
                continue
            local_path = local_dir / Path(key).name
            logger.info("  ↓ s3://%s/%s → %s", bucket, key, local_path)
            s3.download_file(bucket, key, str(local_path))
            downloaded.append(local_path)

    return downloaded


def _upload_outputs(local_output_dir: Path, bucket: str, prefix: str) -> list[str]:
    """Upload every CSV in *local_output_dir* to S3. Returns uploaded keys."""
    s3 = _s3_client()
    uploaded: list[str] = []

    for f in sorted(local_output_dir.glob("*.csv")):
        key = f"{prefix}{f.name}"
        logger.info("  ↑ %s → s3://%s/%s", f.name, bucket, key)
        s3.upload_file(str(f), bucket, key)
        uploaded.append(key)

    return uploaded


# ── resolve event parameters ─────────────────────────────────────────────

def _parse_event(event: dict) -> tuple[str, str, str]:
    """
    Extract (bucket, input_prefix, output_prefix) from:
      a) an S3 event notification, or
      b) a direct-invocation payload.
    Falls back to env vars.
    """
    # S3 event notification format
    records = event.get("Records", [])
    if records and records[0].get("eventSource") == "aws:s3":
        bucket = records[0]["s3"]["bucket"]["name"]
        key = records[0]["s3"]["object"]["key"]
        input_prefix = key.rsplit("/", 1)[0] + "/" if "/" in key else ""
        output_prefix = os.environ.get("S3_OUTPUT_PREFIX", "processed/")
        return bucket, input_prefix, output_prefix

    # Direct invocation
    bucket = event.get("s3_bucket", os.environ.get("S3_BUCKET", ""))
    input_prefix = event.get("s3_input_prefix", os.environ.get("S3_INPUT_PREFIX", "input/"))
    output_prefix = event.get("s3_output_prefix", os.environ.get("S3_OUTPUT_PREFIX", "processed/"))
    return bucket, input_prefix, output_prefix


# ── Lambda handler ───────────────────────────────────────────────────────

def handler(event: dict, context: Any = None) -> dict:
    """
    AWS Lambda entry-point.

    Returns
    -------
    dict  with keys: status, output_files, errors, output_s3_prefix
    """
    logger.info("ETL handler invoked.  Event keys: %s", list(event.keys()))

    bucket, input_prefix, output_prefix = _parse_event(event)

    if not bucket:
        return {
            "status": "error",
            "message": "No S3 bucket provided (event or S3_BUCKET env var).",
        }

    with tempfile.TemporaryDirectory(prefix="conut_etl_") as tmpdir:
        tmp = Path(tmpdir)
        input_dir = tmp / "input"
        input_dir.mkdir()

        # 1. Download raw CSVs
        logger.info("Downloading inputs from s3://%s/%s …", bucket, input_prefix)
        downloaded = _download_inputs(bucket, input_prefix, input_dir)
        logger.info("Downloaded %d CSV files.", len(downloaded))

        if not downloaded:
            return {
                "status": "error",
                "message": f"No CSV files found under s3://{bucket}/{input_prefix}",
            }

        # 2. Run the ETL pipeline against the downloaded files
        #    We redirect the pipeline's OUTPUT_DIR to a temp location.
        from pipelines import run_pipeline

        original_output_dir = run_pipeline.OUTPUT_DIR
        local_output = tmp / "output"
        local_output.mkdir()
        run_pipeline.OUTPUT_DIR = local_output

        try:
            results = run_pipeline.run(str(input_dir), verbose=True)
        finally:
            run_pipeline.OUTPUT_DIR = original_output_dir

        # 3. Upload processed outputs to S3
        logger.info("Uploading outputs to s3://%s/%s …", bucket, output_prefix)
        uploaded = _upload_outputs(local_output, bucket, output_prefix)

    return {
        "status": "success",
        "input_files": len(downloaded),
        "output_files": uploaded,
        "output_s3_prefix": f"s3://{bucket}/{output_prefix}",
    }


# ── local invocation ─────────────────────────────────────────────────────

def run_local(data_dir: str | None = None) -> dict:
    """
    Run the ETL pipeline locally (no S3 involved).
    Useful for development and testing.

    Parameters
    ----------
    data_dir : str, optional
        Path to directory containing raw CSVs.
        Defaults to ``conut_bakery_scaled_data/`` in the project root.

    Returns
    -------
    dict  with keys: status, output_files, output_dir
    """
    from pipelines.run_pipeline import run as etl_run

    if data_dir is None:
        data_dir = str(PROJECT_ROOT / "conut_bakery_scaled_data")

    results = etl_run(data_dir, verbose=True)

    output_dir = str(PROJECT_ROOT / "pipelines" / "output")
    return {
        "status": "success",
        "output_files": list(results.keys()),
        "output_dir": output_dir,
    }


if __name__ == "__main__":
    # Quick local test
    result = run_local()
    print(json.dumps(result, indent=2))
