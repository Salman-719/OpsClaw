"""
Agent brain — AWS Bedrock Converse API with tool-calling loop.

Flow:
  user message → Bedrock → (tool_use)* → tool_result(s) → Bedrock → final text
"""

from __future__ import annotations
import json, logging
from typing import Any

import boto3

from agent import config
from agent.core import SYSTEM_PROMPT
from agent.tools import TOOL_SPECS
from agent.tools.executor import execute_tool

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10  # safety cap to avoid infinite loops


# ---------------------------------------------------------------------------
# Bedrock client (lazy singleton)
# ---------------------------------------------------------------------------
_bedrock_client = None


def _get_client():
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=config.AWS_REGION,
        )
    return _bedrock_client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chat(user_message: str, history: list[dict] | None = None) -> dict:
    """
    Send a user message (with optional history) to Bedrock and return
    the agent's final answer.

    Parameters
    ----------
    user_message : str
    history : list[dict]
        Prior Bedrock-format messages (role + content).

    Returns
    -------
    dict  {"answer": str, "tool_calls": list[dict], "messages": list[dict]}
    """
    client = _get_client()

    # Build conversation
    messages: list[dict] = list(history or [])
    messages.append({
        "role": "user",
        "content": [{"text": user_message}],
    })

    tool_calls_log: list[dict] = []

    for _round in range(MAX_TOOL_ROUNDS):
        resp = client.converse(
            modelId=config.BEDROCK_MODEL_ID,
            system=[{"text": SYSTEM_PROMPT}],
            messages=messages,
            toolConfig={"tools": TOOL_SPECS},
            inferenceConfig={
                "maxTokens": config.BEDROCK_MAX_TOKENS,
                "temperature": config.BEDROCK_TEMPERATURE,
            },
        )

        stop = resp.get("stopReason", "end_turn")
        output_msg = resp["output"]["message"]
        messages.append(output_msg)

        # If we got a final text answer — return
        if stop == "end_turn":
            text_parts = [
                block["text"]
                for block in output_msg["content"]
                if "text" in block
            ]
            return {
                "answer": "\n".join(text_parts),
                "tool_calls": tool_calls_log,
                "messages": messages,
            }

        # Otherwise, process tool calls
        if stop == "tool_use":
            tool_results: list[dict] = []
            for block in output_msg["content"]:
                if "toolUse" not in block:
                    continue
                tu = block["toolUse"]
                name = tu["name"]
                tool_id = tu["toolUseId"]
                params = tu.get("input", {})

                log.info("Tool call: %s(%s)", name, json.dumps(params, default=str))
                result_str = execute_tool(name, params)
                tool_calls_log.append({
                    "tool": name,
                    "input": params,
                    "output_preview": result_str[:500],
                })

                tool_results.append({
                    "toolResultId": tool_id,
                    "content": [{"text": result_str}],
                })

            # Append tool results message
            messages.append({
                "role": "user",
                "content": [{"toolResult": tr} for tr in tool_results],
            })
        else:
            # Unexpected stop reason — break
            text_parts = [
                block.get("text", "")
                for block in output_msg["content"]
                if "text" in block
            ]
            return {
                "answer": "\n".join(text_parts) or "(no response)",
                "tool_calls": tool_calls_log,
                "messages": messages,
            }

    # Safety: exceeded max rounds
    return {
        "answer": "I ran out of reasoning steps — please simplify your question.",
        "tool_calls": tool_calls_log,
        "messages": messages,
    }


# ---------------------------------------------------------------------------
# Local-mode stub (bypasses Bedrock entirely for offline testing)
# ---------------------------------------------------------------------------

def chat_local(user_message: str) -> dict:
    """
    Simple keyword-based dispatcher for LOCAL_MODE testing
    when Bedrock is not available.
    """
    msg = user_message.lower()

    # Pick a tool to call based on keywords
    calls: list[tuple[str, dict]] = []

    if any(k in msg for k in ["forecast", "predict", "demand"]):
        calls.append(("query_forecast", {"compare": True}))
    if any(k in msg for k in ["combo", "pair", "bundle", "association"]):
        calls.append(("query_combos", {}))
    if any(k in msg for k in ["expan", "feasib", "new branch", "open"]):
        calls.append(("query_expansion", {"query_type": "ranking"}))
    if any(k in msg for k in ["staff", "shift", "gap", "understaf"]):
        calls.append(("query_staffing", {"query_type": "top_gaps"}))
    if any(k in msg for k in ["growth", "beverage", "coffee", "milkshake"]):
        calls.append(("query_growth", {"query_type": "ranking"}))
    if any(k in msg for k in ["overview", "summary", "status", "everything"]):
        calls.append(("get_overview", {}))
    if any(k in msg for k in ["recommend", "advice", "suggest", "action"]):
        calls.append(("get_all_recommendations", {}))

    if not calls:
        calls.append(("get_overview", {}))

    tool_calls_log = []
    results = []
    for name, params in calls:
        out = execute_tool(name, params)
        tool_calls_log.append({"tool": name, "input": params, "output_preview": out[:500]})
        results.append(f"**{name}**:\n```json\n{out}\n```")

    return {
        "answer": "\n\n".join(results),
        "tool_calls": tool_calls_log,
        "messages": [],
    }
