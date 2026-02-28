"""
Agent service configuration.
All settings are read from environment variables with sensible defaults.
"""

from __future__ import annotations

import os


# ── AWS ──────────────────────────────────────────────────────────────────
AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")

# ── DynamoDB table names ─────────────────────────────────────────────────
ENV_NAME = os.getenv("ENV_NAME", "dev")
PROJECT = "conut-ops"

FORECAST_TABLE  = os.getenv("DYNAMODB_FORECAST_TABLE",  f"{PROJECT}-forecast-{ENV_NAME}")
COMBO_TABLE     = os.getenv("DYNAMODB_COMBO_TABLE",      f"{PROJECT}-combo-{ENV_NAME}")
EXPANSION_TABLE = os.getenv("DYNAMODB_EXPANSION_TABLE",  f"{PROJECT}-expansion-{ENV_NAME}")
STAFFING_TABLE  = os.getenv("DYNAMODB_STAFFING_TABLE",   f"{PROJECT}-staffing-{ENV_NAME}")
GROWTH_TABLE    = os.getenv("DYNAMODB_GROWTH_TABLE",     f"{PROJECT}-growth-{ENV_NAME}")
# ── S3 + Step Functions (for upload → pipeline trigger) ────────────
S3_DATA_BUCKET = os.getenv("S3_DATA_BUCKET", f"{PROJECT}-data-{ENV_NAME}")
S3_INPUT_PREFIX = os.getenv("S3_INPUT_PREFIX", "input/")
STATE_MACHINE_ARN = os.getenv("STATE_MACHINE_ARN", "")
# ── Bedrock ──────────────────────────────────────────────────────────────
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "eu.amazon.nova-pro-v1:0")
BEDROCK_MAX_TOKENS = int(os.getenv("BEDROCK_MAX_TOKENS", "4096"))
BEDROCK_TEMPERATURE = float(os.getenv("BEDROCK_TEMPERATURE", "0.1"))

# ── Server ───────────────────────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ── Local / offline mode ─────────────────────────────────────────────────
# When True, DynamoDB queries read from local CSV files instead of AWS.
LOCAL_MODE = os.getenv("LOCAL_MODE", "true").lower() in ("1", "true", "yes")
LOCAL_DATA_ROOT = os.getenv("LOCAL_DATA_ROOT", "")  # set at runtime
