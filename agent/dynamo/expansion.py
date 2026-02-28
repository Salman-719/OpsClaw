"""DynamoDB queries for Feature 3 — Expansion Feasibility."""

from __future__ import annotations

import json
from typing import Any

from agent import config
from agent.dynamo import _get_table, _decimal_to_float, _read_local_csv, _df_to_items


BRANCHES = ["batroun", "bliss", "jnah", "tyre"]


def get_branch_kpi(branch: str) -> dict | None:
    """Get KPI row for a branch."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/expansion/output/branch_kpis.csv")
        if df.empty:
            return None
        rows = df[df["branch"] == branch]
        return _df_to_items(rows)[0] if not rows.empty else None

    table = _get_table(config.EXPANSION_TABLE)
    resp = table.get_item(Key={"pk": branch, "sk": "kpi"})
    item = resp.get("Item")
    return _decimal_to_float(item) if item else None


def get_feasibility(branch: str) -> dict | None:
    """Get feasibility score for a branch."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/expansion/output/feasibility_scores.csv")
        if df.empty:
            return None
        rows = df[df["branch"] == branch]
        return _df_to_items(rows)[0] if not rows.empty else None

    table = _get_table(config.EXPANSION_TABLE)
    resp = table.get_item(Key={"pk": branch, "sk": "feasibility"})
    item = resp.get("Item")
    return _decimal_to_float(item) if item else None


def list_all_branches_feasibility() -> list[dict]:
    """Get all branches ranked by feasibility score."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/expansion/output/feasibility_scores.csv")
        if df.empty:
            return []
        df = df.sort_values("feasibility_score", ascending=False)
        return _df_to_items(df)

    results = []
    for branch in BRANCHES:
        item = get_feasibility(branch)
        if item:
            results.append(item)
    results.sort(key=lambda x: x.get("feasibility_score", 0), reverse=True)
    return results


def get_expansion_recommendation() -> dict | None:
    """Get the expansion recommendation."""
    if config.LOCAL_MODE:
        rec_path = _read_local_csv.__wrapped__ if hasattr(_read_local_csv, '__wrapped__') else None
        from pathlib import Path
        root = Path(config.LOCAL_DATA_ROOT) if config.LOCAL_DATA_ROOT else Path(__file__).resolve().parent.parent.parent
        fp = root / "analytics" / "expansion" / "output" / "recommendation.json"
        if fp.exists():
            return json.loads(fp.read_text())
        return None

    table = _get_table(config.EXPANSION_TABLE)
    resp = table.get_item(Key={"pk": "recommendation", "sk": "expansion"})
    item = resp.get("Item")
    if not item:
        return None
    item = _decimal_to_float(item)
    # Parse JSON strings back to dicts
    for key in ("region_scores", "growth_summary"):
        if key in item and isinstance(item[key], str):
            try:
                item[key] = json.loads(item[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return item


def get_all_kpis() -> list[dict]:
    """Get KPIs for all branches."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/expansion/output/branch_kpis.csv")
        return _df_to_items(df) if not df.empty else []

    results = []
    for branch in BRANCHES:
        item = get_branch_kpi(branch)
        if item:
            results.append(item)
    return results
