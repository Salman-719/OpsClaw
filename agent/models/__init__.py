"""
Pydantic models for request / response schemas.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User question")
    session_id: str | None = Field(None, description="Optional session ID for history")


class ToolCallInfo(BaseModel):
    tool: str
    input: dict[str, Any] = {}
    output_preview: str = ""


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCallInfo] = []


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardOverview(BaseModel):
    forecast: Any = None
    top_combos: Any = None
    expansion_ranking: Any = None
    staffing_summary: Any = None
    growth_ranking: Any = None


class DashboardSection(BaseModel):
    """Generic wrapper for any single-feature dashboard payload."""
    feature: str
    data: Any
