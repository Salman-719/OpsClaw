"""
parsing.py – Safe, multi-format parser for items_list column.

Handles:
  * Python/JSON list literals:  "['item a', 'item b']"
  * Plain comma-separated:      "item a, item b"
  * Quoted comma-separated:     '"item a","item b"'
  * Already a Python list:      ['item a', 'item b']
"""
from __future__ import annotations

import ast
import json
import re
from typing import List

from .utils import get_logger

_log = get_logger(__name__)


def _normalize_item(s: str) -> str:
    """Strip whitespace and lowercase a single item string."""
    return re.sub(r"\s+", " ", s.strip().lower())


def parse_items_list(raw) -> List[str]:
    """
    Parse an *items_list* value into a clean list of normalised item strings.

    Parameters
    ----------
    raw : str | list | None
        The raw value from the DataFrame cell.

    Returns
    -------
    list[str]
        Possibly empty list; never raises.
    """
    if raw is None or (isinstance(raw, float)):  # NaN comes in as float
        return []

    # Already a Python list (shouldn't happen with CSV but guard anyway)
    if isinstance(raw, list):
        return [_normalize_item(str(x)) for x in raw if str(x).strip()]

    raw = str(raw).strip()
    if not raw or raw.lower() in {"nan", "none", "[]", ""}:
        return []

    # --- Attempt 1: ast.literal_eval (handles Python list literals) ---
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, (list, tuple)):
            return [_normalize_item(str(x)) for x in parsed if str(x).strip()]
        if isinstance(parsed, str):
            return [_normalize_item(parsed)] if parsed.strip() else []
    except (ValueError, SyntaxError):
        pass

    # --- Attempt 2: json.loads (handles JSON arrays) ---
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [_normalize_item(str(x)) for x in parsed if str(x).strip()]
    except (json.JSONDecodeError, ValueError):
        pass

    # --- Attempt 3: strip surrounding brackets then split on commas ---
    cleaned = raw.strip("[](){} ")
    # Split on comma; each token may have surrounding quotes
    parts = re.split(r",\s*", cleaned)
    items = []
    for part in parts:
        part = part.strip().strip("'\"")
        if part:
            items.append(_normalize_item(part))
    return items
