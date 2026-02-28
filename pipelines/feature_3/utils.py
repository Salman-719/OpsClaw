"""
utils.py
========
Shared utilities for Feature 3 – Expansion Feasibility.

Covers:
  - Branch name normalisation (raw report strings → canonical short names)
  - Region mapping (canonical branch → north/south/beirut)
  - Numeric parsing helpers
  - Logging setup
"""

from __future__ import annotations

import re
import logging
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────────────────────

def get_logger(name: str = "feature_3") -> logging.Logger:
    """Return a consistently formatted logger for the feature."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s – %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


# ──────────────────────────────────────────────────────────────────────────────
# BRANCH NORMALISATION
# ──────────────────────────────────────────────────────────────────────────────

# Explicit mapping: any string containing these substrings → canonical name.
# Applied in order (most specific first).
# Keys are lowercase substrings; values are canonical short names.
_BRANCH_SUBSTRING_MAP: list[tuple[str, str]] = [
    ("main street",  "batroun"),   # "Main Street Coffee" / "Conut Main Street (Batroun)"
    ("batroun",      "batroun"),
    ("bliss",        "bliss"),
    ("jnah",         "jnah"),
    ("tyre",         "tyre"),
    ("conut",        "bliss"),     # bare "Conut" → the oldest/original Bliss branch
]

# Canonical set – used for validation downstream
CANONICAL_BRANCHES: frozenset[str] = frozenset({"batroun", "bliss", "jnah", "tyre"})


def normalise_branch(raw: str) -> Optional[str]:
    """
    Map a raw branch name string to a canonical short name.

    Returns None if no mapping is found (unknown branch).

    Rules (applied top-to-bottom on the *lowercase* raw string):
      "main street" or "batroun"  → "batroun"
      "bliss"                     → "bliss"
      "jnah"                      → "jnah"
      "tyre"                      → "tyre"
      bare "conut" (fallthrough)  → "bliss"   (original Bliss store)
    """
    if not raw or not isinstance(raw, str):
        return None
    s = raw.lower().strip()
    # Strip leading "branch name:" or "branch :" prefixes that appear in report headers
    s = re.sub(r"^branch\s*(name\s*)?:\s*", "", s).strip()
    for substring, canonical in _BRANCH_SUBSTRING_MAP:
        if substring in s:
            return canonical
    return None


# ──────────────────────────────────────────────────────────────────────────────
# REGION MAPPING
# ──────────────────────────────────────────────────────────────────────────────

REGION_MAP: dict[str, str] = {
    "batroun": "north",
    "tyre":    "south",
    "bliss":   "beirut",
    "jnah":    "beirut",
}

BEIRUT_BRANCHES: frozenset[str] = frozenset({"bliss", "jnah"})


def get_region(branch: str) -> str:
    """Return 'north' | 'south' | 'beirut' | 'unknown' for a canonical branch."""
    return REGION_MAP.get(branch, "unknown")


# ──────────────────────────────────────────────────────────────────────────────
# NUMERIC HELPERS
# ──────────────────────────────────────────────────────────────────────────────

_NUM_RE = re.compile(r"^-?[\d,]+\.?\d*$")


def parse_number(value: str) -> Optional[float]:
    """
    Parse a numeric string that may contain commas, surrounding quotes, or
    extra whitespace.  Returns None on failure.
    """
    if value is None:
        return None
    cleaned = str(value).strip().replace('"', "").replace(",", "").strip()
    if not cleaned or cleaned in ("-", ""):
        return None
    if _NUM_RE.match(cleaned):
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def parse_duration_hms(s: str) -> Optional[float]:
    """
    Parse a duration string in HH.MM.SS or HH:MM:SS format to decimal hours.
    Returns None on failure.
    """
    s = s.strip()
    sep = "." if "." in s else ":"
    parts = s.split(sep)
    if len(parts) != 3:
        return None
    try:
        h, m, sec = int(parts[0]), int(parts[1]), int(parts[2])
        return h + m / 60.0 + sec / 3600.0
    except ValueError:
        return None
