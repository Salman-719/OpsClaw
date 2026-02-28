"""DynamoDB queries for Feature 4 — Staffing Estimation."""

from __future__ import annotations

from typing import Any

from agent import config
from agent.dynamo import _get_table, _decimal_to_float, _read_local_csv, _df_to_items


BRANCHES = ["Conut - Tyre", "Conut Jnah", "Main Street Coffee"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def get_staffing_findings(branch: str) -> dict | None:
    """Get the branch-level staffing summary."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/staffing/output/branch_staffing_findings.csv")
        if df.empty:
            return None
        rows = df[df["branch"] == branch]
        return _df_to_items(rows)[0] if not rows.empty else None

    table = _get_table(config.STAFFING_TABLE)
    resp = table.get_item(Key={"pk": branch, "sk": "findings"})
    item = resp.get("Item")
    return _decimal_to_float(item) if item else None


def get_all_findings() -> list[dict]:
    """Get staffing findings for all branches."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/staffing/output/branch_staffing_findings.csv")
        return _df_to_items(df) if not df.empty else []

    results = []
    for branch in BRANCHES:
        item = get_staffing_findings(branch)
        if item:
            results.append(item)
    return results


def get_staffing_gaps(branch: str, day: str | None = None) -> list[dict]:
    """Get hourly staffing gaps for a branch, optionally filtered by day."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/staffing/output/staffing_gap_hourly.csv")
        if df.empty:
            return []
        mask = df["branch"] == branch
        if day:
            mask &= df["day_of_week"] == day
        # Only non-balanced for relevance
        if "status" in df.columns:
            mask &= df["status"] != "balanced"
        result = df[mask].sort_values(["day_of_week", "hour"])
        # Select key columns only
        cols = ["branch", "day_of_week", "hour", "avg_active_employees",
                "required_employees_base", "gap_base", "status", "explanation"]
        cols = [c for c in cols if c in result.columns]
        return _df_to_items(result[cols])

    from boto3.dynamodb.conditions import Key
    table = _get_table(config.STAFFING_TABLE)
    if day:
        resp = table.query(
            KeyConditionExpression=Key("pk").eq(branch) & Key("sk").begins_with(f"gap#{day}"),
        )
    else:
        resp = table.query(
            KeyConditionExpression=Key("pk").eq(branch) & Key("sk").begins_with("gap#"),
        )
    return [_decimal_to_float(i) for i in resp.get("Items", [])]


def get_worst_gaps(branch: str, top_n: int = 5) -> list[dict]:
    """Get the N worst understaffed slots for a branch."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/staffing/output/staffing_gap_hourly.csv")
        if df.empty:
            return []
        mask = (df["branch"] == branch) & (df["status"] == "understaffed")
        result = df[mask].nlargest(top_n, "gap_base")
        cols = ["branch", "day_of_week", "hour", "avg_active_employees",
                "required_employees_base", "gap_base", "status", "explanation"]
        cols = [c for c in cols if c in result.columns]
        return _df_to_items(result[cols])

    gaps = get_staffing_gaps(branch)
    understaffed = [g for g in gaps if g.get("status") == "understaffed"]
    understaffed.sort(key=lambda x: x.get("gap_base", 0), reverse=True)
    return understaffed[:top_n]


def get_staffing_summary_view() -> list[dict]:
    """Get the compact branch summary view."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/staffing/output/branch_summary_view.csv")
        return _df_to_items(df) if not df.empty else []
    return get_all_findings()


def get_top_gap_slots() -> list[dict]:
    """Get the pre-computed top gap slots across all branches."""
    if config.LOCAL_MODE:
        df = _read_local_csv("analytics/staffing/output/top_gap_slots.csv")
        return _df_to_items(df) if not df.empty else []
    # Fallback: aggregate from all branches
    all_gaps = []
    for branch in BRANCHES:
        all_gaps.extend(get_worst_gaps(branch, top_n=3))
    all_gaps.sort(key=lambda x: abs(x.get("gap_base", 0)), reverse=True)
    return all_gaps
