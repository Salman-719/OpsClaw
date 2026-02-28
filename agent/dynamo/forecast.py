"""DynamoDB queries for Feature 2 — Demand Forecast."""

from __future__ import annotations

from typing import Any

from agent import config
from agent.dynamo import _get_table, _decimal_to_float, _read_local_csv, _df_to_items


BRANCHES = ["Conut", "Conut - Tyre", "Conut Jnah", "Main Street Coffee"]
SCENARIOS = ["base", "optimistic"]


def get_forecast(branch: str, scenario: str = "base", period: int = 1) -> dict | None:
    """Get a single forecast row."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/forecast/output/demand_forecast_all.csv")
        if df.empty:
            return None
        mask = (
            (df["branch"] == branch)
            & (df["scenario"] == scenario)
            & (df["forecast_period"] == period)
        )
        rows = df[mask]
        if rows.empty:
            return None
        return _df_to_items(rows)[0]

    table = _get_table(config.FORECAST_TABLE)
    resp = table.get_item(Key={"pk": f"{branch}#{scenario}", "sk": f"period#{period}"})
    item = resp.get("Item")
    return _decimal_to_float(item) if item else None


def list_forecasts(branch: str) -> list[dict]:
    """Get all forecast rows (both scenarios, all periods) for a branch."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/forecast/output/demand_forecast_all.csv")
        if df.empty:
            return []
        rows = df[df["branch"] == branch]
        return _df_to_items(rows)

    from boto3.dynamodb.conditions import Key
    table = _get_table(config.FORECAST_TABLE)
    items = []
    for scenario in SCENARIOS:
        resp = table.query(
            KeyConditionExpression=Key("pk").eq(f"{branch}#{scenario}"),
        )
        items.extend(resp.get("Items", []))
    return [_decimal_to_float(i) for i in items]


def compare_branches_primary() -> list[dict]:
    """Get the primary (period=1, base) forecast for every branch."""
    results = []
    for branch in BRANCHES:
        row = get_forecast(branch, "base", 1)
        if row:
            results.append(row)
    return results


def get_all_forecasts() -> list[dict]:
    """Get all 24 forecast rows."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/forecast/output/demand_forecast_all.csv")
        return _df_to_items(df) if not df.empty else []

    items = []
    for branch in BRANCHES:
        items.extend(list_forecasts(branch))
    return items
