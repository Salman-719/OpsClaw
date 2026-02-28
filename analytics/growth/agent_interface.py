"""
agent_interface.py – Agent-facing query handler for Feature 5.

Supported query_type values
---------------------------
"underperforming_branches"
    Returns branches ranked by beverage_attachment_rate ascending (worst first),
    with the gap to the best-performing branch.

"highest_growth_potential"
    Returns branches ranked by potential_score descending, with reasons.

"beverage_gap"
    Returns the best-performing branch and per-branch gap figures.

Usage
-----
    from pipelines.feature_5.agent_interface import handle_query

    result = handle_query("underperforming_branches", {})
    result = handle_query("highest_growth_potential", {"top_n": 3})
    result = handle_query("beverage_gap", {})
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .utils import get_logger, repo_root

_log = get_logger(__name__)

# Cache so subsequent calls within the same process don't reload from disk
_CACHE: Dict[str, Any] = {}


def _load_outputs() -> Dict[str, Any]:
    """Load pre-computed CSVs from analytics/growth/output/."""
    if _CACHE:
        return _CACHE

    import pandas as pd

    out_dir = Path(__file__).resolve().parent / "output"
    if not out_dir.exists():
        raise FileNotFoundError(
            f"analytics/growth/output/ not found at {out_dir}. "
            "Run the pipeline first:  python -m analytics.growth.run"
        )

    _CACHE["kpis"] = pd.read_csv(out_dir / "branch_beverage_kpis.csv")
    _CACHE["growth"] = pd.read_csv(out_dir / "branch_growth_potential.csv")
    _CACHE["rules"] = pd.read_csv(out_dir / "assoc_rules_by_branch.csv")

    rec_path = out_dir / "recommendation.json"
    if rec_path.exists():
        with open(rec_path, "r", encoding="utf-8") as fh:
            _CACHE["recommendation"] = json.load(fh)

    return _CACHE


def _df_to_records(df) -> list:
    """Convert DataFrame to JSON-serialisable list of dicts."""
    return json.loads(df.to_json(orient="records"))


def handle_query(query_type: str, payload: dict) -> dict:
    """
    Dispatch a query and return a structured dict result.

    Parameters
    ----------
    query_type : str
        One of: "underperforming_branches", "highest_growth_potential",
        "beverage_gap".
    payload : dict
        Optional parameters, e.g. {"top_n": 5}.

    Returns
    -------
    dict
        {"query_type": ..., "result": ..., "meta": ...}
    """
    _log.info("handle_query called: type=%r payload=%r", query_type, payload)
    data = _load_outputs()
    top_n = int(payload.get("top_n", 10))

    # ------------------------------------------------------------------
    if query_type == "underperforming_branches":
        kpis = data["kpis"].copy()
        ranked = (
            kpis.sort_values("beverage_attachment_rate", ascending=True)
            .head(top_n)[
                [
                    "branch",
                    "total_orders",
                    "beverage_orders",
                    "beverage_attachment_rate",
                    "beverage_gap_to_best",
                ]
            ]
        )
        return {
            "query_type": query_type,
            "result": _df_to_records(ranked),
            "meta": {
                "description": (
                    "Branches ranked worst-to-best on beverage attachment rate. "
                    "'beverage_gap_to_best' shows how far each branch lags the leader."
                ),
                "total_branches": len(kpis),
            },
        }

    # ------------------------------------------------------------------
    elif query_type == "highest_growth_potential":
        growth = data["growth"].copy()
        cols = [
            c
            for c in [
                "branch",
                "potential_score",
                "potential_rank",
                "beverage_attachment_rate",
                "total_orders",
                "top_bundle_rule",
                "beverage_gap_to_best",
            ]
            if c in growth.columns
        ]
        ranked = growth.sort_values("potential_score", ascending=False).head(top_n)[cols]
        return {
            "query_type": query_type,
            "result": _df_to_records(ranked),
            "meta": {
                "description": (
                    "Branches ranked by composite growth potential score (0-1). "
                    "Score combines: low current attachment, large order volume, "
                    "and strong food→beverage association lift."
                ),
                "score_components": "low_attachment (35%) + order_volume (35%) + assoc_lift (30%)",
            },
        }

    # ------------------------------------------------------------------
    elif query_type == "beverage_gap":
        kpis = data["kpis"].copy()
        best_row = kpis.loc[kpis["beverage_attachment_rate"].idxmax()]
        per_branch = kpis[
            ["branch", "beverage_attachment_rate", "beverage_gap_to_best", "total_orders"]
        ].sort_values("beverage_gap_to_best", ascending=False)
        return {
            "query_type": query_type,
            "result": {
                "best_branch": best_row["branch"],
                "best_branch_rate": float(best_row["beverage_attachment_rate"]),
                "per_branch_gap": _df_to_records(per_branch),
            },
            "meta": {
                "description": (
                    "Best branch sets the benchmark. "
                    "'beverage_gap_to_best' = best_rate - branch_rate. "
                    "A gap of 0.10 means the branch attaches beverages in 10% fewer orders."
                )
            },
        }

    # ------------------------------------------------------------------
    else:
        supported = ["underperforming_branches", "highest_growth_potential", "beverage_gap"]
        _log.error("Unknown query_type: %r", query_type)
        return {
            "query_type": query_type,
            "error": f"Unknown query_type '{query_type}'. Supported: {supported}",
        }


def clear_cache() -> None:
    """Clear the in-memory output cache (useful after re-running the pipeline)."""
    _CACHE.clear()
    _log.info("Output cache cleared.")
