"""
Upload routes — presigned S3 upload URLs + pipeline trigger.

POST /api/upload/prepare   → archive old S3 data + reset DynamoDB tables
POST /api/upload/presign   → get a presigned PUT URL for S3
POST /api/upload/trigger   → start the Step Functions pipeline
POST /api/upload/status    → check pipeline execution status
"""

from __future__ import annotations
import json, logging
from datetime import datetime, timezone

import boto3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent import config

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/upload", tags=["upload"])

# ---------------------------------------------------------------------------
# Lazy AWS clients
# ---------------------------------------------------------------------------
_s3_client = None
_sfn_client = None
_dynamo_resource = None


def _s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=config.AWS_REGION)
    return _s3_client


def _sfn():
    global _sfn_client
    if _sfn_client is None:
        _sfn_client = boto3.client("stepfunctions", region_name=config.AWS_REGION)
    return _sfn_client


def _dynamo():
    global _dynamo_resource
    if _dynamo_resource is None:
        _dynamo_resource = boto3.resource("dynamodb", region_name=config.AWS_REGION)
    return _dynamo_resource


# ---------------------------------------------------------------------------
# Helpers — S3 archive
# ---------------------------------------------------------------------------

def _archive_prefix(bucket: str, src_prefix: str, archive_root: str) -> int:
    """
    Move all objects under *src_prefix* to *archive_root*/<src_prefix>.
    Returns number of objects archived.
    """
    s3 = _s3()
    paginator = s3.get_paginator("list_objects_v2")
    count = 0

    for page in paginator.paginate(Bucket=bucket, Prefix=src_prefix):
        for obj in page.get("Contents", []):
            src_key = obj["Key"]
            dest_key = f"{archive_root}{src_key}"
            log.info("  archive: %s → %s", src_key, dest_key)
            s3.copy_object(
                Bucket=bucket,
                CopySource={"Bucket": bucket, "Key": src_key},
                Key=dest_key,
            )
            s3.delete_object(Bucket=bucket, Key=src_key)
            count += 1

    return count


# ---------------------------------------------------------------------------
# Helpers — DynamoDB reset
# ---------------------------------------------------------------------------

ALL_TABLES = [
    config.FORECAST_TABLE,
    config.COMBO_TABLE,
    config.EXPANSION_TABLE,
    config.STAFFING_TABLE,
    config.GROWTH_TABLE,
]


def _clear_table(table_name: str) -> int:
    """Scan-and-delete all items from a DynamoDB table. Returns deleted count."""
    table = _dynamo().Table(table_name)
    # Get the key schema so we know which attributes to use for delete
    key_attrs = [k["AttributeName"] for k in table.key_schema]

    deleted = 0
    scan_kwargs: dict = {"ProjectionExpression": ", ".join(key_attrs)}

    while True:
        resp = table.scan(**scan_kwargs)
        items = resp.get("Items", [])
        if not items:
            break

        with table.batch_writer() as batch:
            for item in items:
                key = {k: item[k] for k in key_attrs}
                batch.delete_item(Key=key)
                deleted += 1

        # Continue scanning if there are more items
        if "LastEvaluatedKey" in resp:
            scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        else:
            break

    log.info("  cleared %d items from %s", deleted, table_name)
    return deleted


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PrepareResponse(BaseModel):
    archived_files: int
    cleared_tables: dict[str, int]
    archive_path: str


class PresignRequest(BaseModel):
    filename: str = Field(..., min_length=1, description="CSV filename to upload")


class PresignResponse(BaseModel):
    upload_url: str
    s3_key: str
    bucket: str
    expires_in: int = 300


class TriggerRequest(BaseModel):
    s3_key: str = Field("", description="Optional specific key. Default: use input/ prefix.")


class TriggerResponse(BaseModel):
    execution_arn: str
    status: str
    started_at: str


class StatusRequest(BaseModel):
    execution_arn: str


class PipelineStatus(BaseModel):
    execution_arn: str
    status: str
    started_at: str | None = None
    stopped_at: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/prepare", response_model=PrepareResponse)
async def prepare_for_upload():
    """
    Prepare the system for new data ingestion:
      1. Archive all existing files under input/, processed/, results/
         to archive/<timestamp>/
      2. Clear all 5 DynamoDB tables so fresh analytics can be written
    Call this BEFORE uploading new CSV files.
    """
    if config.LOCAL_MODE:
        raise HTTPException(400, "Prepare not available in LOCAL_MODE")

    bucket = config.S3_DATA_BUCKET
    if not bucket:
        raise HTTPException(500, "S3_DATA_BUCKET not configured")

    try:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_root = f"archive/{ts}/"

        # 1. Archive S3 prefixes
        total_archived = 0
        for prefix in ("input/", "processed/", "results/"):
            count = _archive_prefix(bucket, prefix, archive_root)
            total_archived += count
            log.info("Archived %d objects from %s", count, prefix)

        # 2. Clear DynamoDB tables
        cleared: dict[str, int] = {}
        for table_name in ALL_TABLES:
            if table_name:
                cleared[table_name] = _clear_table(table_name)

        return PrepareResponse(
            archived_files=total_archived,
            cleared_tables=cleared,
            archive_path=f"s3://{bucket}/{archive_root}",
        )
    except Exception as exc:
        log.exception("Prepare failed")
        raise HTTPException(500, str(exc))

@router.post("/presign", response_model=PresignResponse)
async def presign_upload(req: PresignRequest):
    """Generate a presigned PUT URL for uploading a CSV to S3."""
    if config.LOCAL_MODE:
        raise HTTPException(400, "Upload not available in LOCAL_MODE")

    bucket = config.S3_DATA_BUCKET
    if not bucket:
        raise HTTPException(500, "S3_DATA_BUCKET not configured")

    # Clean filename
    safe_name = req.filename.strip().replace(" ", "_")
    if not safe_name.lower().endswith(".csv"):
        safe_name += ".csv"

    s3_key = f"{config.S3_INPUT_PREFIX}{safe_name}"

    try:
        url = _s3().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": bucket,
                "Key": s3_key,
                "ContentType": "text/csv",
            },
            ExpiresIn=300,
        )
        return PresignResponse(
            upload_url=url,
            s3_key=s3_key,
            bucket=bucket,
            expires_in=300,
        )
    except Exception as exc:
        log.exception("Presign failed")
        raise HTTPException(500, str(exc))


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_pipeline(req: TriggerRequest):
    """Start the Step Functions pipeline execution."""
    if config.LOCAL_MODE:
        raise HTTPException(400, "Pipeline trigger not available in LOCAL_MODE")

    sfn_arn = config.STATE_MACHINE_ARN
    if not sfn_arn:
        raise HTTPException(500, "STATE_MACHINE_ARN not configured")

    try:
        now = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        resp = _sfn().start_execution(
            stateMachineArn=sfn_arn,
            name=f"upload-{now}",
            input=json.dumps({
                "s3_bucket": config.S3_DATA_BUCKET,
                "s3_input_prefix": config.S3_INPUT_PREFIX,
                "s3_output_prefix": "processed/",
            }),
        )
        return TriggerResponse(
            execution_arn=resp["executionArn"],
            status="RUNNING",
            started_at=resp["startDate"].isoformat(),
        )
    except Exception as exc:
        log.exception("Pipeline trigger failed")
        raise HTTPException(500, str(exc))


@router.post("/status", response_model=PipelineStatus)
async def pipeline_status(req: StatusRequest):
    """Check status of a pipeline execution."""
    if config.LOCAL_MODE:
        raise HTTPException(400, "Pipeline status not available in LOCAL_MODE")

    try:
        resp = _sfn().describe_execution(executionArn=req.execution_arn)
        return PipelineStatus(
            execution_arn=resp["executionArn"],
            status=resp["status"],
            started_at=resp["startDate"].isoformat() if "startDate" in resp else None,
            stopped_at=resp["stopDate"].isoformat() if "stopDate" in resp else None,
        )
    except Exception as exc:
        log.exception("Status check failed")
        raise HTTPException(500, str(exc))
