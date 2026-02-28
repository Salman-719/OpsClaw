"""
agent_interface.py
==================
Feature 3 – Expansion Feasibility  |  Agent / ClawBot Query Interface

Provides `handle_query(query_type, payload)` returning structured JSON-like dicts.

SUPPORTED QUERY TYPES:
  "expansion_recommendation"  – Overall feasibility + recommended region + reasoning
  "branch_ranking"            – Branches ranked by feasibility score
  "growth_summary"            – Growth trend per branch + whether sales are increasing
  "feasibility_explanation"   – KPI breakdown + weight rationale
  "risk_summary"              – Volatility / risk level per branch

USAGE (programmatic):
    from pipelines.feature_3.agent_interface import ClawbotExpansionInterface

    agent = ClawbotExpansionInterface.from_outputs("outputs/feature_3")

    result = agent.handle_query("expansion_recommendation")
    result = agent.handle_query("branch_ranking")
    result = agent.handle_query("growth_summary")
    result = agent.handle_query("feasibility_explanation", {"branch": "tyre"})
    result = agent.handle_query("risk_summary")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .utils import get_logger, get_region
from .scoring import WEIGHTS, WEIGHT_RATIONALE

logger = get_logger("feature_3.agent_interface")


# ──────────────────────────────────────────────────────────────────────────────
# RESPONSE HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _ok(data: Any) -> dict:
    return {"status": "ok", "data": data}


def _err(msg: str) -> dict:
    return {"status": "error", "message": msg}


# ──────────────────────────────────────────────────────────────────────────────
# MAIN INTERFACE CLASS
# ──────────────────────────────────────────────────────────────────────────────

class ClawbotExpansionInterface:
    """
    Thin stateless interface over pre-computed artifact files.

    Parameters
    ----------
    feasibility_scores : pd.DataFrame  – output of scoring.compute_feasibility_scores
    branch_kpis        : pd.DataFrame  – output of kpis.build_branch_kpis
    recommendation     : dict          – output of recommend.build_recommendation
    """

    def __init__(
        self,
        feasibility_scores: pd.DataFrame,
        branch_kpis: pd.DataFrame,
        recommendation: dict,
    ):
        self._scores      = feasibility_scores.set_index("branch")
        self._kpis        = branch_kpis.set_index("branch")
        self._rec         = recommendation

    # ── Factory ─────────────────────────────────────────────────────────────

    @classmethod
    def from_outputs(cls, outputs_dir: str | Path) -> "ClawbotExpansionInterface":
        """
        Load pre-computed artifacts from the outputs directory.

        Expected files:
          feasibility_scores.csv
          branch_kpis.csv
          recommendation.json
        """
        d = Path(outputs_dir)
        scores = pd.read_csv(d / "feasibility_scores.csv")
        kpis   = pd.read_csv(d / "branch_kpis.csv")
        with open(d / "recommendation.json", "r", encoding="utf-8") as f:
            rec = json.load(f)
        return cls(scores, kpis, rec)

    # ── Dispatch ─────────────────────────────────────────────────────────────

    def handle_query(
        self,
        query_type: str,
        payload: dict | None = None,
    ) -> dict:
        """
        Route a query and return a structured dict.

        Parameters
        ----------
        query_type : one of the supported query type strings (see module docstring)
        payload    : optional dict with query-specific parameters

        Returns
        -------
        dict with keys: status ("ok" | "error"), data (or message)
        """
        payload = payload or {}
        handlers = {
            "expansion_recommendation": self._expansion_recommendation,
            "branch_ranking":           self._branch_ranking,
            "growth_summary":           self._growth_summary,
            "feasibility_explanation":  self._feasibility_explanation,
            "risk_summary":             self._risk_summary,
        }
        handler = handlers.get(query_type)
        if handler is None:
            return _err(
                f"Unknown query_type '{query_type}'. "
                f"Supported: {list(handlers.keys())}"
            )
        try:
            return _ok(handler(payload))
        except Exception as exc:
            logger.exception("handle_query error for '%s'", query_type)
            return _err(str(exc))

    # ── Q1: Expansion recommendation ────────────────────────────────────────

    def _expansion_recommendation(self, payload: dict) -> dict:
        """
        "Is opening a new branch feasible right now? Provide overall feasibility + reasoning."
        "Which location/region should we expand into next (North/South/Beirut) and why?"
        """
        rec = self._rec
        best_branch = rec["best_branch_to_replicate"]
        overall     = rec["overall_feasibility"]
        tier        = rec["feasibility_tier"]

        # Is expansion feasible overall?
        feasible = tier in ("High", "Medium")
        feasibility_statement = (
            f"Expansion is currently {'feasible' if feasible else 'marginal'} "
            f"(top branch score: {overall:.4f}, tier: {tier})."
        )

        return {
            "feasible":                 feasible,
            "feasibility_statement":    feasibility_statement,
            "recommended_region":       rec["recommended_region"],
            "candidate_locations":      rec["candidate_locations"],
            "best_branch_to_replicate": best_branch,
            "region_scores":            rec["region_scores"],
            "reasoning":                rec["reasoning"],
            "warning":                  rec["warning"],
        }

    # ── Q2: Branch ranking ───────────────────────────────────────────────────

    def _branch_ranking(self, payload: dict) -> dict:
        """
        "Rank branches by expansion feasibility score."
        """
        fs = self._scores.reset_index()
        ranking = []
        for rank, (_, row) in enumerate(
            fs.sort_values("feasibility_score", ascending=False).iterrows(), start=1
        ):
            ranking.append({
                "rank":              rank,
                "branch":            row["branch"],
                "region":            get_region(row["branch"]),
                "feasibility_score": round(float(row["feasibility_score"]), 4),
                "score_tier":        row.get("score_tier", "N/A"),
                "top_drivers":       row.get("top_drivers", "N/A"),
            })
        return {"ranking": ranking}

    # ── Q3: Growth summary ───────────────────────────────────────────────────

    def _growth_summary(self, payload: dict) -> dict:
        """
        "Is sales increasing in each branch? Which branch shows strongest growth trend?"
        """
        growth_map = self._rec.get("growth_summary", {})

        summary = []
        for branch, info in sorted(
            growth_map.items(), key=lambda x: x[1]["growth_rate"], reverse=True
        ):
            pct = info.get("pct_change")
            summary.append({
                "branch":      branch,
                "region":      get_region(branch),
                "growth_rate": info["growth_rate"],
                "pct_change":  pct,
                "is_growing":  info["is_growing"],
                "statement":   (
                    f"Sales in {branch.title()} are "
                    f"{'INCREASING' if info['is_growing'] else 'DECLINING or FLAT'} "
                    f"(growth rate: {info['growth_rate']:+.4f}"
                    + (f", {pct*100:+.1f}% first-to-last" if pct is not None else "")
                    + ")."
                ),
            })

        strongest = summary[0]["branch"] if summary else "N/A"
        return {
            "strongest_growth_branch": strongest,
            "growth_supports_expansion": (
                f"Increasing sales in {strongest.title()} strengthens the case to open a new branch "
                f"in the {'same region: ' + get_region(strongest).title() + ' Lebanon' if get_region(strongest) != 'unknown' else 'vicinity'}."
            ),
            "branch_growth": summary,
        }

    # ── Q4: Feasibility explanation ──────────────────────────────────────────

    def _feasibility_explanation(self, payload: dict) -> dict:
        """
        "What KPIs drove the recommendation (top contributing metrics)?"
        Optionally scoped to a specific --branch.
        """
        branch = payload.get("branch")

        if branch:
            branch = branch.lower()
            # Try to match branch name
            try:
                from .utils import normalise_branch
                nb = normalise_branch(branch) or branch
                if nb not in self._scores.index:
                    return {"error": f"Branch '{branch}' not found. Available: {self._scores.index.tolist()}"}
                row = self._scores.loc[nb]
                single = {
                    "branch":            nb,
                    "feasibility_score": round(float(row["feasibility_score"]), 4),
                    "score_tier":        row.get("score_tier", "N/A"),
                    "components": {
                        "growth (weight=0.30)":       round(float(row.get("norm_growth", 0.5)), 4),
                        "revenue (weight=0.25)":      round(float(row.get("norm_revenue", 0.5)), 4),
                        "stability (weight=0.15)":    round(float(row.get("stability", 0.5)), 4),
                        "avg_order (weight=0.15)":    round(float(row.get("norm_avg_order", 0.5)), 4),
                        "delivery (weight=0.10)":     round(float(row.get("norm_delivery", 0.5)), 4),
                        "ops_eff (weight=0.05)":      round(float(row.get("norm_ops_eff", 0.5)), 4),
                    },
                    "top_drivers": row.get("top_drivers", "N/A"),
                }
                return {"branch_explanation": single, "weight_rationale": WEIGHT_RATIONALE}
            except Exception as exc:
                return {"error": str(exc)}

        # All branches
        explanations = []
        for br, row in self._scores.iterrows():
            explanations.append({
                "branch":            br,
                "feasibility_score": round(float(row["feasibility_score"]), 4),
                "score_tier":        row.get("score_tier", "N/A"),
                "top_drivers":       row.get("top_drivers", "N/A"),
                "components": {
                    "growth (weight=0.30)":    round(float(row.get("norm_growth", 0.5)), 4),
                    "revenue (weight=0.25)":   round(float(row.get("norm_revenue", 0.5)), 4),
                    "stability (weight=0.15)": round(float(row.get("stability", 0.5)), 4),
                    "avg_order (weight=0.15)": round(float(row.get("norm_avg_order", 0.5)), 4),
                    "delivery (weight=0.10)":  round(float(row.get("norm_delivery", 0.5)), 4),
                    "ops_eff (weight=0.05)":   round(float(row.get("norm_ops_eff", 0.5)), 4),
                },
            })
        return {
            "all_branches": explanations,
            "weights":      WEIGHTS,
            "weight_rationale": WEIGHT_RATIONALE,
        }

    # ── Q5: Risk summary ─────────────────────────────────────────────────────

    def _risk_summary(self, payload: dict) -> dict:
        """
        "What is the risk level (volatility) for each branch?"
        """
        risk_levels = []
        for br, row in self._scores.sort_values("norm_volatility", ascending=False).iterrows():
            raw_vol = self._kpis.loc[br, "revenue_volatility"] if br in self._kpis.index else None
            norm_v  = float(row.get("norm_volatility", 0.5))
            risk_tier = "High" if norm_v >= 0.65 else "Medium" if norm_v >= 0.35 else "Low"
            risk_levels.append({
                "branch":            br,
                "region":            get_region(br),
                "revenue_volatility": round(float(raw_vol), 4) if raw_vol is not None else None,
                "norm_volatility":   round(norm_v, 4),
                "risk_tier":         risk_tier,
                "stability_score":   round(1.0 - norm_v, 4),
                "statement": (
                    f"{br.title()} has {risk_tier.lower()} revenue risk "
                    f"(volatility CV: {f'{raw_vol:.4f}' if raw_vol is not None else 'N/A'}, "
                    f"stability: {(1-norm_v):.4f})."
                ),
            })
        return {"risk_by_branch": risk_levels}
