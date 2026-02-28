"""
Dashboard routes — read-only GET endpoints for the frontend.
"""

from __future__ import annotations
from fastapi import APIRouter

from agent.models import DashboardOverview, DashboardSection
from agent.dynamo import forecast, combo, expansion, staffing, growth

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverview)
async def overview():
    """Cross-feature executive overview for the main dashboard."""
    return DashboardOverview(
        forecast=forecast.compare_branches_primary(),
        top_combos=combo.get_top_combos(5),
        expansion_ranking=expansion.list_all_branches_feasibility(),
        staffing_summary=staffing.get_staffing_summary_view(),
        growth_ranking=growth.list_growth_potential(),
    )


@router.get("/forecast", response_model=DashboardSection)
async def dashboard_forecast():
    return DashboardSection(feature="forecast", data=forecast.get_all_forecasts())


@router.get("/forecast/{branch}", response_model=DashboardSection)
async def dashboard_forecast_branch(branch: str):
    return DashboardSection(feature="forecast", data=forecast.list_forecasts(branch))


@router.get("/combo", response_model=DashboardSection)
async def dashboard_combo():
    return DashboardSection(feature="combo", data=combo.get_top_combos(20))


@router.get("/combo/{branch}", response_model=DashboardSection)
async def dashboard_combo_branch(branch: str):
    return DashboardSection(feature="combo", data=combo.get_branch_combos(branch, 20))


@router.get("/expansion", response_model=DashboardSection)
async def dashboard_expansion():
    return DashboardSection(
        feature="expansion",
        data={
            "ranking": expansion.list_all_branches_feasibility(),
            "recommendation": expansion.get_expansion_recommendation(),
        },
    )


@router.get("/expansion/{branch}", response_model=DashboardSection)
async def dashboard_expansion_branch(branch: str):
    return DashboardSection(
        feature="expansion",
        data={
            "kpis": expansion.get_branch_kpi(branch),
            "feasibility": expansion.get_feasibility(branch),
        },
    )


@router.get("/staffing", response_model=DashboardSection)
async def dashboard_staffing():
    return DashboardSection(
        feature="staffing",
        data={
            "summary": staffing.get_staffing_summary_view(),
            "top_gaps": staffing.get_top_gap_slots(),
        },
    )


@router.get("/staffing/{branch}", response_model=DashboardSection)
async def dashboard_staffing_branch(branch: str):
    return DashboardSection(
        feature="staffing",
        data={
            "findings": staffing.get_staffing_findings(branch),
            "worst_gaps": staffing.get_worst_gaps(branch, 10),
        },
    )


@router.get("/growth", response_model=DashboardSection)
async def dashboard_growth():
    return DashboardSection(
        feature="growth",
        data={
            "ranking": growth.list_growth_potential(),
            "recommendation": growth.get_growth_recommendation(),
        },
    )


@router.get("/growth/{branch}", response_model=DashboardSection)
async def dashboard_growth_branch(branch: str):
    return DashboardSection(
        feature="growth",
        data={
            "kpis": growth.get_beverage_kpi(branch),
            "potential": growth.get_growth_potential(branch),
            "rules": growth.get_bundle_rules(branch),
        },
    )
