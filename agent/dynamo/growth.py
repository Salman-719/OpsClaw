"""DynamoDB queries for Feature 5 — Growth Strategy."""

from __future__ import annotations

import json
from typing import Any

from agent import config
from agent.dynamo import _get_table, _decimal_to_float, _read_local_csv, _df_to_items


BRANCHES = ["Conut - Tyre", "Conut Jnah", "Main Street Coffee"]


def get_beverage_kpi(branch: str) -> dict | None:
    """Get beverage attachment KPIs for a branch."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/growth/output/branch_beverage_kpis.csv")
        if df.empty:
            return None
        rows = df[df["branch"] == branch]
        return _df_to_items(rows)[0] if not rows.empty else None

    table = _get_table(config.GROWTH_TABLE)
    resp = table.get_item(Key={"pk": branch, "sk": "beverage_kpi"})
    item = resp.get("Item")
    return _decimal_to_float(item) if item else None


def get_all_beverage_kpis() -> list[dict]:
    """Get beverage KPIs for all branches."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/growth/output/branch_beverage_kpis.csv")
        return _df_to_items(df) if not df.empty else []

    results = []
    for branch in BRANCHES:
        item = get_beverage_kpi(branch)
        if item:
            results.append(item)
    return results


def get_growth_potential(branch: str) -> dict | None:
    """Get growth potential ranking for a branch."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/growth/output/branch_growth_potential.csv")
        if df.empty:
            return None
        rows = df[df["branch"] == branch]
        return _df_to_items(rows)[0] if not rows.empty else None

    table = _get_table(config.GROWTH_TABLE)
    resp = table.get_item(Key={"pk": branch, "sk": "growth_potential"})
    item = resp.get("Item")
    return _decimal_to_float(item) if item else None


def list_growth_potential() -> list[dict]:
    """Get growth potential for all branches, ranked."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/growth/output/branch_growth_potential.csv")
        if df.empty:
            return []
        df = df.sort_values("potential_rank")
        return _df_to_items(df)

    results = []
    for branch in BRANCHES:
        item = get_growth_potential(branch)
        if item:
            results.append(item)
    results.sort(key=lambda x: x.get("potential_rank", 999))
    return results


def get_bundle_rules(branch: str, min_lift: float = 1.0, top_n: int = 10) -> list[dict]:
    """Get association rules for a branch, filtered by lift."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/growth/output/assoc_rules_by_branch.csv")
        if df.empty:
            return []
        mask = (df["branch"] == branch) & (df["lift"] >= min_lift)
        result = df[mask].nlargest(top_n, "lift")
        return _df_to_items(result)

    from boto3.dynamodb.conditions import Key
    table = _get_table(config.GROWTH_TABLE)
    resp = table.query(
        KeyConditionExpression=Key("pk").eq(branch) & Key("sk").begins_with("rule#"),
    )
    items = [_decimal_to_float(i) for i in resp.get("Items", [])]
    items = [i for i in items if i.get("lift", 0) >= min_lift]
    items.sort(key=lambda x: x.get("lift", 0), reverse=True)
    return items[:top_n]


def get_growth_recommendation() -> dict | None:
    """Get the overall growth strategy recommendation."""
    if config.LOCAL_MODE:
        from pathlib import Path
        root = Path(config.LOCAL_DATA_ROOT) if config.LOCAL_DATA_ROOT else Path(__file__).resolve().parent.parent.parent
        fp = root / "analytics" / "growth" / "output" / "recommendation.json"
        if fp.exists():
            return json.loads(fp.read_text())
        return None

    table = _get_table(config.GROWTH_TABLE)
    resp = table.get_item(Key={"pk": "recommendation", "sk": "growth"})
    item = resp.get("Item")
    if not item:
        return None
    item = _decimal_to_float(item)
    for key in ("key_findings", "branch_actions"):
        if key in item and isinstance(item[key], str):
            try:
                item[key] = json.loads(item[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return item
