"""
Upload routes — presigned S3 upload URLs + pipeline trigger.

POST /api/upload/presign   → get a presigned PUT URL for S3
POST /api/upload/trigger   → start the Step Functions pipeline
GET  /api/upload/status    → check pipeline execution status
"""

from __future__ import annotations
import json, logging
from datetime import datetime

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


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

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
