"""
Chat route — POST /api/chat
"""

from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException

from agent import config
from agent.models import ChatRequest, ChatResponse, ToolCallInfo
from agent.core.agent import chat, chat_local

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Natural-language Q&A powered by OpsClaw agent."""
    try:
        if config.LOCAL_MODE:
            result = chat_local(req.message)
        else:
            result = chat(req.message)

        return ChatResponse(
            answer=result["answer"],
            tool_calls=[ToolCallInfo(**tc) for tc in result.get("tool_calls", [])],
        )
    except Exception as exc:
        log.exception("Chat failed")
        raise HTTPException(status_code=500, detail=str(exc))
