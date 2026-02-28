"""
recommend.py
============
Feature 3 – Expansion Feasibility  |  Regional Recommendation Logic

Geography-aware recommendation engine.

REGION MAP:
  batroun → north
  tyre    → south
  bliss   → beirut
  jnah    → beirut

RULES (applied in order):
  1. Compute region scores: average feasibility of branches in each region.
  2. Identify the branch with the strongest growth trend.
  3. Identify the branch with the highest feasibility score.

  4. If north_score is highest OR batroun growth is the strongest across all branches:
       → Recommend "North (Batroun-like market)"
         "Sales are increasing in Batroun; replicating this profile in North Lebanon
          strengthens the case for a new branch."

  5. If south_score is highest OR tyre growth is the strongest:
       → Recommend "South (Tyre-like market)"

  6. If beirut_score is highest:
       → Recommend Beirut expansion — BUT since Bliss and Jnah are geographically
          close, explicitly warn against duplication:
          "Avoid opening another branch near Bliss/Jnah; target a different
           Beirut neighbourhood (e.g. Hamra, Verdun, Ashrafieh) or consider
           operational capacity improvements first."

  7. If current best branch has positive growth → reinforce recommendation
     ("Sales are increasing → strengthens case to replicate this profile.")
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .utils import get_logger, get_region, REGION_MAP, BEIRUT_BRANCHES

logger = get_logger("feature_3.recommend")


# ──────────────────────────────────────────────────────────────────────────────
# REGION SCORING
# ──────────────────────────────────────────────────────────────────────────────

def compute_region_scores(feasibility_scores: pd.DataFrame) -> dict[str, float]:
    """
    Average feasibility score per region.

    Returns dict: {"north": float, "south": float, "beirut": float, ...}
    """
    fs = feasibility_scores.copy().set_index("branch")
    fs["region"] = fs.index.map(get_region)
    region_scores = (
        fs.groupby("region")["feasibility_score"]
        .mean()
        .round(4)
        .to_dict()
    )
    logger.info("region_scores: %s", region_scores)
    return region_scores


# ──────────────────────────────────────────────────────────────────────────────
# RECOMMENDATION
# ──────────────────────────────────────────────────────────────────────────────

def build_recommendation(
    feasibility_scores: pd.DataFrame,
    branch_kpis: pd.DataFrame,
) -> dict[str, Any]:
    """
    Produce a structured recommendation dict.

    Parameters
    ----------
    feasibility_scores : output of scoring.compute_feasibility_scores()
    branch_kpis        : output of kpis.build_branch_kpis()

    Returns
    -------
    dict with keys:
        recommended_region         : str
        candidate_locations        : list[str]
        best_branch_to_replicate   : str
        feasibility_tier           : str
        overall_feasibility        : float     (top-branch score)
        region_scores              : dict
        growth_summary             : dict[branch → {growth_rate, is_growing}]
        reasoning                  : list[str]  (bullet points)
        warning                    : str | None
        raw_scores                 : list[dict]
    """
    fs = feasibility_scores.copy().set_index("branch")
    kp = branch_kpis.copy().set_index("branch")

    region_scores = compute_region_scores(feasibility_scores)

    # Best branch overall
    best_branch = fs["feasibility_score"].idxmax()
    best_score  = float(fs.loc[best_branch, "feasibility_score"])
    best_tier   = str(fs.loc[best_branch, "score_tier"])

    # Growth data per branch
    growth_col  = "recent_growth_rate" if "recent_growth_rate" in kp.columns else None
    growth_map: dict[str, dict] = {}
    for br in kp.index:
        gr = float(kp.loc[br, "recent_growth_rate"]) if growth_col else 0.0
        growth_map[br] = {
            "growth_rate":  round(gr, 6),
            "is_growing":   gr > 0,
            "pct_change":   round(float(kp.loc[br, "pct_change_first_last"]), 4)
                            if "pct_change_first_last" in kp.columns else None,
        }

    # Which branch has the strongest growth?
    strongest_growth_branch = max(growth_map.items(), key=lambda x: x[1]["growth_rate"])[0]

    # ── Determine recommended region ───────────────────────────────────────
    best_region     = max(region_scores, key=region_scores.get) if region_scores else "unknown"
    batroun_growth  = growth_map.get("batroun", {}).get("growth_rate", 0.0)
    tyre_growth     = growth_map.get("tyre",    {}).get("growth_rate", 0.0)

    reasoning: list[str] = []
    warning:   str | None = None
    candidate_locations: list[str] = []

    if best_region == "north" or strongest_growth_branch == "batroun":
        recommended_region  = "North Lebanon"
        candidate_locations = ["Batroun region", "Byblos", "Tripoli"]
        reasoning.append(
            f"North (Batroun) has the {'highest' if best_region == 'north' else 'strongest-growing'} "
            f"regional score ({region_scores.get('north', 'N/A'):.4f})."
        )
        if batroun_growth > 0:
            reasoning.append(
                f"Sales in Batroun are INCREASING (growth rate: {batroun_growth:+.4f}). "
                "Positive growth trend strongly supports opening a new branch in North Lebanon — "
                "replicating the Batroun branch profile."
            )

    elif best_region == "south" or strongest_growth_branch == "tyre":
        recommended_region  = "South Lebanon"
        candidate_locations = ["Tyre region", "Sidon", "Nabatieh"]
        reasoning.append(
            f"South (Tyre) has the {'highest' if best_region == 'south' else 'strongest-growing'} "
            f"regional score ({region_scores.get('south', 'N/A'):.4f})."
        )
        if tyre_growth > 0:
            reasoning.append(
                f"Sales in Tyre are INCREASING (growth rate: {tyre_growth:+.4f}). "
                "Positive growth trend strongly supports opening a new branch in South Lebanon — "
                "replicating the Tyre branch profile."
            )

    else:
        # Beirut is best region
        recommended_region  = "Beirut"
        candidate_locations = ["Hamra", "Verdun", "Ashrafieh", "Mar Mikhael"]
        reasoning.append(
            f"Beirut has the highest regional score ({region_scores.get('beirut', 'N/A'):.4f})."
        )
        best_beirut = (
            fs[fs.index.map(get_region) == "beirut"]["feasibility_score"].idxmax()
            if any(get_region(b) == "beirut" for b in fs.index) else None
        )
        if best_beirut:
            bgr = growth_map.get(best_beirut, {}).get("growth_rate", 0.0)
            if bgr > 0:
                reasoning.append(
                    f"Sales in {best_beirut.title()} (Beirut) are INCREASING (growth rate: {bgr:+.4f}). "
                    "Increasing demand in Beirut supports expansion."
                )
        warning = (
            "⚠️  Bliss and Jnah are geographically close (~3 km). "
            "Opening another branch near either would risk cannibalisation. "
            "Recommended approach: target a different Beirut neighbourhood "
            "(e.g., Hamra, Verdun, Ashrafieh, Mar Mikhael) OR prioritise "
            "operational capacity improvements at the existing branches before "
            "committing to a new location."
        )
        reasoning.append(
            "Bliss and Jnah are close — a new Beirut branch should be in "
            "a distinct neighbourhood to avoid customer overlap."
        )

    # ── Best branch to replicate ─────────────────────────────────────────
    in_recommended_region = [
        b for b in fs.index if get_region(b) == best_region
    ]
    if in_recommended_region:
        best_branch_to_replicate = fs.loc[in_recommended_region, "feasibility_score"].idxmax()
    else:
        best_branch_to_replicate = best_branch

    # ── Generic reasoning about overall best branch ─────────────────────
    reasoning.append(
        f"Best-scored branch overall: {best_branch.title()} "
        f"(score={best_score:.4f}, tier={best_tier})."
    )
    reasoning.append(
        f"Strongest growth branch: {strongest_growth_branch.title()} "
        f"(growth_rate={growth_map[strongest_growth_branch]['growth_rate']:+.4f})."
    )

    # ── Raw scores list ──────────────────────────────────────────────────
    raw_scores = (
        fs.reset_index()[["branch", "feasibility_score", "score_tier",
                           "norm_growth", "norm_revenue", "stability",
                           "norm_avg_order", "norm_delivery", "norm_ops_eff"]]
        .rename(columns={"norm_growth": "w_growth", "norm_revenue": "w_revenue",
                         "norm_avg_order": "w_avg_order",
                         "norm_delivery": "w_delivery", "norm_ops_eff": "w_ops_eff"})
        .to_dict(orient="records")
    )

    recommendation = {
        "recommended_region":       recommended_region,
        "candidate_locations":      candidate_locations,
        "best_branch_to_replicate": best_branch_to_replicate,
        "feasibility_tier":         best_tier,
        "overall_feasibility":      best_score,
        "region_scores":            region_scores,
        "growth_summary":           growth_map,
        "reasoning":                reasoning,
        "warning":                  warning,
        "raw_scores":               raw_scores,
    }

    logger.info(
        "recommendation: region=%s, replicate=%s, tier=%s",
        recommended_region, best_branch_to_replicate, best_tier,
    )
    return recommendation
