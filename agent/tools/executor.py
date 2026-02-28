"""
Tool executor — maps Bedrock tool_use names to dynamo query functions.
"""

from __future__ import annotations
import json, logging
from typing import Any

from agent.dynamo import combo, forecast, expansion, staffing, growth

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Individual tool dispatchers
# ---------------------------------------------------------------------------

def _exec_query_forecast(params: dict) -> dict:
    if params.get("compare"):
        return {"comparison": forecast.compare_branches_primary()}

    branch = params.get("branch")
    if not branch:
        return {"all_forecasts": forecast.get_all_forecasts()}

    scenario = params.get("scenario", "base")
    period = params.get("period", 1)
    result = forecast.get_forecast(branch, scenario, period)
    if result:
        return result
    # fallback: list all for the branch
    return {"branch": branch, "forecasts": forecast.list_forecasts(branch)}


def _exec_query_combos(params: dict) -> dict:
    scope = params.get("scope")
    branch = params.get("branch")
    min_lift = params.get("min_lift", 1.0)
    top_n = params.get("top_n", 10)

    if scope:
        return {"scope": scope, "pairs": combo.get_combo_pairs(scope, min_lift, top_n)}
    if branch:
        return {"branch": branch, "pairs": combo.get_branch_combos(branch, top_n)}
    # overall top
    return {"top_combos": combo.get_top_combos(top_n)}


def _exec_query_expansion(params: dict) -> dict:
    qt = params["query_type"]
    branch = params.get("branch", "").lower()

    if qt == "kpi":
        return {"branch": branch, "kpis": expansion.get_branch_kpi(branch)}
    if qt == "feasibility":
        return {"branch": branch, "feasibility": expansion.get_feasibility(branch)}
    if qt == "ranking":
        return {"ranking": expansion.list_all_branches_feasibility()}
    if qt == "recommendation":
        return {"recommendation": expansion.get_expansion_recommendation()}
    if qt == "all_kpis":
        return {"all_kpis": expansion.get_all_kpis()}
    return {"error": f"unknown query_type '{qt}'"}


def _exec_query_staffing(params: dict) -> dict:
    qt = params["query_type"]
    branch = params.get("branch")
    day = params.get("day")
    top_n = params.get("top_n", 5)

    if qt == "findings":
        return {"branch": branch, "findings": staffing.get_staffing_findings(branch)}
    if qt == "all_findings":
        return {"all_findings": staffing.get_all_findings()}
    if qt == "gaps":
        return {"branch": branch, "day": day, "gaps": staffing.get_staffing_gaps(branch, day)}
    if qt == "worst_gaps":
        return {"branch": branch, "worst_gaps": staffing.get_worst_gaps(branch, top_n)}
    if qt == "top_gaps":
        return {"top_gaps": staffing.get_top_gap_slots()}
    return {"error": f"unknown query_type '{qt}'"}


def _exec_query_growth(params: dict) -> dict:
    qt = params["query_type"]
    branch = params.get("branch")
    min_lift = params.get("min_lift", 1.0)
    top_n = params.get("top_n", 10)

    if qt == "kpi":
        return {"branch": branch, "kpis": growth.get_beverage_kpi(branch)}
    if qt == "all_kpis":
        return {"all_kpis": growth.get_all_beverage_kpis()}
    if qt == "potential":
        return {"branch": branch, "potential": growth.get_growth_potential(branch)}
    if qt == "ranking":
        return {"ranking": growth.list_growth_potential()}
    if qt == "rules":
        return {"branch": branch, "rules": growth.get_bundle_rules(branch, min_lift, top_n)}
    if qt == "recommendation":
        return {"recommendation": growth.get_growth_recommendation()}
    return {"error": f"unknown query_type '{qt}'"}


def _exec_get_overview(_params: dict) -> dict:
    """Cross-feature executive snapshot."""
    return {
        "forecast": forecast.compare_branches_primary(),
        "top_combos": combo.get_top_combos(5),
        "expansion_ranking": expansion.list_all_branches_feasibility(),
        "staffing_summary": staffing.get_staffing_summary_view(),
        "growth_ranking": growth.list_growth_potential(),
    }


def _exec_get_all_recommendations(_params: dict) -> dict:
    return {
        "expansion": expansion.get_expansion_recommendation(),
        "growth": growth.get_growth_recommendation(),
        "staffing_top_gaps": staffing.get_top_gap_slots(),
        "top_combos": combo.get_top_combos(5),
    }


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_DISPATCH: dict[str, Any] = {
    "query_forecast":          _exec_query_forecast,
    "query_combos":            _exec_query_combos,
    "query_expansion":         _exec_query_expansion,
    "query_staffing":          _exec_query_staffing,
    "query_growth":            _exec_query_growth,
    "get_overview":            _exec_get_overview,
    "get_all_recommendations": _exec_get_all_recommendations,
}


def execute_tool(name: str, params: dict) -> str:
    """Run a tool by name and return JSON string result."""
    fn = _DISPATCH.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = fn(params)
        return json.dumps(result, default=str)
    except Exception as exc:
        log.exception("Tool %s failed", name)
        return json.dumps({"error": str(exc)})
