"""DynamoDB queries for Feature 1 — Combo Optimization."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from agent import config
from agent.dynamo import _get_table, _decimal_to_float, _read_local_csv, _df_to_items


def get_combo_pairs(
    scope: str = "overall",
    min_lift: float = 1.0,
    top_n: int = 20,
) -> list[dict]:
    """Return combo pairs for a scope, filtered by min lift, sorted by lift desc."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/combo/data/artifacts/combo_pairs_explained.csv")
        if df.empty:
            df = _read_local_csv("analytics/combo/data/artifacts/combo_pairs.csv")
        if df.empty:
            return []
        mask = df["scope"] == scope
        if min_lift > 0:
            mask &= df["lift"] >= min_lift
        result = df[mask].nlargest(top_n, "lift")
        return _df_to_items(result)

    table = _get_table(config.COMBO_TABLE)
    from boto3.dynamodb.conditions import Key, Attr
    resp = table.query(
        KeyConditionExpression=Key("pk").eq(scope),
    )
    items = [_decimal_to_float(i) for i in resp.get("Items", [])]
    items = [i for i in items if i.get("lift", 0) >= min_lift]
    items.sort(key=lambda x: x.get("lift", 0), reverse=True)
    return items[:top_n]


def get_top_combos(top_n: int = 10) -> list[dict]:
    """Return the top N combo pairs across all scopes (overall scope)."""
    return get_combo_pairs(scope="overall", min_lift=1.0, top_n=top_n)


def get_branch_combos(branch: str, top_n: int = 10) -> list[dict]:
    """Return top combo pairs for a specific branch."""
    return get_combo_pairs(scope=f"branch:{branch}", min_lift=1.0, top_n=top_n)


def list_scopes() -> list[str]:
    """List all available scopes."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/combo/data/artifacts/combo_pairs_explained.csv")
        if df.empty:
            df = _read_local_csv("analytics/combo/data/artifacts/combo_pairs.csv")
        if df.empty:
            return []
        return sorted(df["scope"].unique().tolist())

    table = _get_table(config.COMBO_TABLE)
    resp = table.scan(ProjectionExpression="pk")
    return sorted(set(i["pk"] for i in resp.get("Items", [])))
