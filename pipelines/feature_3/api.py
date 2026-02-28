"""
api.py
======
Feature 3 – Expansion Feasibility  |  FastAPI Router Stub

Provides a FastAPI router with 4 endpoints that delegate to
ClawbotExpansionInterface.handle_query().

Usage:
    # Mount into a main FastAPI app:
    from pipelines.feature_3.api import build_router
    router = build_router("outputs/feature_3")
    app.include_router(router)

    # Or run standalone for testing:
    uvicorn pipelines.feature_3.api:standalone_app --reload

All endpoints return { "status": "ok"|"error", "data": {...} }.

ENDPOINTS:
    POST /expansion/recommendation   – Q1: overall feasibility + region advice
    GET  /expansion/ranking          – Q2: branches ranked by score
    GET  /expansion/growth           – Q3: growth trend per branch
    GET  /expansion/explanation      – Q4: KPI → score breakdown
    GET  /expansion/risk             – Q5: volatility / risk per branch
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

try:
    from fastapi import APIRouter, Query
    from fastapi import FastAPI
    from pydantic import BaseModel
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

from .agent_interface import ClawbotExpansionInterface
from .utils import get_logger

logger = get_logger("feature_3.api")

# ──────────────────────────────────────────────────────────────────────────────
# REQUEST / RESPONSE SCHEMAS
# ──────────────────────────────────────────────────────────────────────────────

if _FASTAPI_AVAILABLE:
    class RecommendationRequest(BaseModel):
        """No required fields – all defaults apply."""
        pass

    class ExplanationRequest(BaseModel):
        branch: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# ROUTER FACTORY
# ──────────────────────────────────────────────────────────────────────────────

def build_router(outputs_dir: str = "outputs/feature_3") -> Any:
    """
    Build and return a FastAPI APIRouter loaded with artifacts from outputs_dir.

    Raises ImportError if FastAPI is not installed.
    """
    if not _FASTAPI_AVAILABLE:
        raise ImportError(
            "FastAPI is not installed. Run: pip install fastapi uvicorn"
        )

    agent = ClawbotExpansionInterface.from_outputs(outputs_dir)
    router = APIRouter(prefix="/expansion", tags=["Expansion Feasibility"])

    # ── POST /expansion/recommendation ──────────────────────────────────────
    @router.post("/recommendation", summary="Overall expansion feasibility + recommended region")
    def recommendation():
        """
        Q1 + Q2: Is opening a new branch feasible? Which region / location?

        Returns feasibility tier, recommended region, candidate locations,
        best branch profile to replicate, and full reasoning chain.
        """
        return agent.handle_query("expansion_recommendation")

    # ── GET /expansion/ranking ───────────────────────────────────────────────
    @router.get("/ranking", summary="Branches ranked by expansion feasibility score")
    def ranking():
        """
        Q3: Rank all branches by composite feasibility score (highest first).
        """
        return agent.handle_query("branch_ranking")

    # ── GET /expansion/growth ────────────────────────────────────────────────
    @router.get("/growth", summary="Sales growth trend per branch")
    def growth():
        """
        Q4: Is revenue increasing in each branch?
        Returns growth rates, direction (growing/declining), and which branch
        shows the strongest trend — with a statement about expansion implications.
        """
        return agent.handle_query("growth_summary")

    # ── GET /expansion/explanation ───────────────────────────────────────────
    @router.get("/explanation", summary="KPI breakdown that drove each branch score")
    def explanation(branch: Optional[str] = Query(default=None, description="Filter to a specific branch")):
        """
        Q5: What KPIs drove the recommendation?
        Optionally filter to a single branch with ?branch=tyre
        """
        return agent.handle_query("feasibility_explanation", {"branch": branch})

    # ── GET /expansion/risk ──────────────────────────────────────────────────
    @router.get("/risk", summary="Revenue volatility / risk level per branch")
    def risk():
        """
        Q6: What is the risk level for each branch?
        Returns revenue volatility, normalised risk score, and risk tier.
        """
        return agent.handle_query("risk_summary")

    return router


# ──────────────────────────────────────────────────────────────────────────────
# STANDALONE APP (for quick testing)
# ──────────────────────────────────────────────────────────────────────────────

def _make_standalone_app(outputs_dir: str = "outputs/feature_3") -> Any:
    if not _FASTAPI_AVAILABLE:
        raise ImportError("FastAPI is not installed.")
    app = FastAPI(
        title="Conut Ops – Feature 3: Expansion Feasibility",
        description="Rule-based expansion feasibility scoring for Conut branches.",
        version="1.0.0",
    )
    app.include_router(build_router(outputs_dir))
    return app


# Expose standalone_app for `uvicorn pipelines.feature_3.api:standalone_app`
try:
    standalone_app = _make_standalone_app()
except Exception:
    standalone_app = None   # No-op if artifacts don't exist yet
