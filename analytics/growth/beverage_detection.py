"""
beverage_detection.py – Keyword-based beverage classification.

Configurable keyword lists identify which items are beverages and
which sub-type they belong to (coffee / milkshake / other_bev).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Configurable keyword registry
# ---------------------------------------------------------------------------

BEVERAGE_KEYWORDS: Dict[str, List[str]] = {
    "coffee": [
        "coffee",
        "espresso",
        "cappuccino",
        "latte",
        "mocha",
        "americano",
        "macchiato",
        "cortado",
        "ristretto",
        "frappe",
        "cold brew",
        "flat white",
        "affogato",
        "lungo",
        "doppio",
        "cafe",
        "caffe",
    ],
    "milkshake": [
        "milkshake",
        "milk shake",
        "shake",
        "smoothie",
    ],
    "other_bev": [
        "juice",
        "lemonade",
        "tea",
        "matcha",
        "hot chocolate",
        "chocolate drink",
        "soda",
        "water",
        "drink",
        "beverage",
    ],
}

# Items to exclude even if they match a keyword (e.g., sauce flavourings)
_EXCLUDE_PATTERNS: List[str] = [
    r"\bsauce\b",
    r"\btopping\b",
    r"\bpaste\b",
    r"\bpowder\b",
    r"\bsyrup\b",
    r"\bflavour\b",
    r"\bfilling\b",
]


def _compile_keywords(keywords: List[str]) -> re.Pattern:
    """Compile a list of keywords into a single regex pattern."""
    escaped = [re.escape(kw) for kw in sorted(keywords, key=len, reverse=True)]
    return re.compile(r"(?:^|[\s\-])(?:" + "|".join(escaped) + r")(?:[\s\-]|$)")


_COMPILED: Dict[str, re.Pattern] = {
    cat: _compile_keywords(kws) for cat, kws in BEVERAGE_KEYWORDS.items()
}
_EXCLUDE_RE = re.compile("|".join(_EXCLUDE_PATTERNS))


def classify_item(item: str) -> Optional[str]:
    """
    Return the beverage category of *item* or ``None`` if not a beverage.

    Parameters
    ----------
    item : str
        Normalised (lowercase, stripped) item name.

    Returns
    -------
    str | None
        One of ``"coffee"``, ``"milkshake"``, ``"other_bev"``, or ``None``.
    """
    if _EXCLUDE_RE.search(item):
        return None
    for category, pattern in _COMPILED.items():
        if pattern.search(f" {item} "):  # pad to ensure boundary matching
            return category
    return None


def is_beverage(item: str) -> bool:
    """Return True if *item* is any type of beverage."""
    return classify_item(item) is not None


def is_target_beverage(item: str) -> bool:
    """Return True if *item* is coffee or milkshake (the target beverages)."""
    return classify_item(item) in {"coffee", "milkshake"}


def beverage_subtype(item: str) -> Optional[str]:
    """Return 'coffee', 'milkshake', 'other_bev', or None."""
    return classify_item(item)
