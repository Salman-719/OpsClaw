"""Shared DynamoDB resource + local-CSV fallback."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from agent import config

_resource = None


def _get_table(table_name: str):
    """Return a boto3 DynamoDB Table resource (lazy-init)."""
    global _resource
    if _resource is None:
        import boto3
        _resource = boto3.resource("dynamodb", region_name=config.AWS_REGION)
    return _resource.Table(table_name)


# ── helpers ──────────────────────────────────────────────────────────────

def _decimal_to_float(obj: Any) -> Any:
    """Convert Decimal values to float for JSON serialisation."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


# ── local CSV reader (offline / demo mode) ───────────────────────────────

_CSV_CACHE: dict[str, pd.DataFrame] = {}


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _read_local_csv(rel_path: str) -> pd.DataFrame:
    """Read a CSV relative to project root, with caching."""
    if rel_path in _CSV_CACHE:
        return _CSV_CACHE[rel_path]
    root = Path(config.LOCAL_DATA_ROOT) if config.LOCAL_DATA_ROOT else _project_root()
    fp = root / rel_path
    if not fp.exists():
        return pd.DataFrame()
    df = pd.read_csv(fp)
    _CSV_CACHE[rel_path] = df
    return df


def _df_to_items(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame rows to list of dicts (JSON-safe)."""
    records = df.to_dict(orient="records")
    clean = []
    for rec in records:
        clean.append({k: (None if pd.isna(v) else v) for k, v in rec.items()})
    return clean
