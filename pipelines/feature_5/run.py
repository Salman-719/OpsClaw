"""
run.py – Feature 5 end-to-end pipeline entrypoint.

Usage
-----
# Full pipeline:
    python -m pipelines.feature_5.run --data_dir "pipelines/output"

# Override output dir:
    python -m pipelines.feature_5.run --data_dir "pipelines/output" --out_dir "outputs/feature_5"

# Smoke-test agent queries (requires outputs to exist):
    python -m pipelines.feature_5.run --smoke_test

# One-liner agent test (after pipeline has been run):
    python -c "from pipelines.feature_5.agent_interface import handle_query; import json; print(json.dumps(handle_query('underperforming_branches', {}), indent=2))"
    python -c "from pipelines.feature_5.agent_interface import handle_query; import json; print(json.dumps(handle_query('highest_growth_potential', {}), indent=2))"
    python -c "from pipelines.feature_5.agent_interface import handle_query; import json; print(json.dumps(handle_query('beverage_gap', {}), indent=2))"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from .agent_interface import clear_cache, handle_query
from .basket_analysis import compute_rules_by_branch
from .kpis import compute_basket_kpis, compute_revenue_kpis, merge_kpis
from .loader import load_all
from .scoring import compute_growth_potential
from .utils import get_logger, repo_root, resolve_output_dir

_log = get_logger("feature_5.run")

# ---------------------------------------------------------------------------
# Recommendation helpers
# ---------------------------------------------------------------------------

def _build_recommendation(growth_df: pd.DataFrame, rules_df: pd.DataFrame) -> dict:
    """Build a structured recommendation.json payload."""
    top = growth_df.iloc[0] if not growth_df.empty else None
    worst = growth_df.iloc[-1] if not growth_df.empty else None
    best_bev = (
        growth_df.sort_values("beverage_attachment_rate", ascending=False).iloc[0]
        if "beverage_attachment_rate" in growth_df.columns and not growth_df.empty
        else None
    )

    rec = {
        "strategy": "Coffee & Milkshake Combo Uplift",
        "objective": "Increase beverage attachment rate across branches via targeted cross-sell",
        "key_findings": [],
        "branch_actions": [],
    }

    if top is not None:
        rec["key_findings"].append(
            f"Highest growth potential: {top['branch']} "
            f"(potential_score={top['potential_score']:.3f}, "
            f"current attachment={top.get('beverage_attachment_rate', 'N/A')})"
        )

    if best_bev is not None:
        rec["key_findings"].append(
            f"Best beverage branch benchmark: {best_bev['branch']} "
            f"(attachment_rate={best_bev['beverage_attachment_rate']:.3f})"
        )

    for _, row in growth_df.iterrows():
        action = {
            "branch": row["branch"],
            "potential_score": float(row.get("potential_score", 0)),
            "current_attachment_rate": float(row.get("beverage_attachment_rate", 0)),
            "beverage_gap_to_best": float(row.get("beverage_gap_to_best", 0)),
            "recommended_bundle": row.get("top_bundle_rule", ""),
            "action": (
                "Priority cross-sell: promote beverage bundles at checkout"
                if float(row.get("potential_score", 0)) >= 0.5
                else "Maintain existing bundle promotions and monitor"
            ),
        }
        rec["branch_actions"].append(action)

    return rec


def _build_summary(
    kpis_df: pd.DataFrame,
    growth_df: pd.DataFrame,
    rules_df: pd.DataFrame,
) -> str:
    lines = [
        "# Feature 5: Coffee & Milkshake Growth Strategy",
        "## Beverage Attachment Summary",
        "",
    ]

    if not kpis_df.empty:
        best = kpis_df.sort_values("beverage_attachment_rate", ascending=False).iloc[0]
        worst = kpis_df.sort_values("beverage_attachment_rate", ascending=True).iloc[0]
        lines += [
            f"- **Best branch**: {best['branch']} — {best['beverage_attachment_rate']:.1%} attachment rate",
            f"- **Most-lagging branch**: {worst['branch']} — {worst['beverage_attachment_rate']:.1%} "
            f"(gap to best: {worst['beverage_gap_to_best']:.1%})",
            "",
        ]

    lines.append("## Growth Potential Ranking")
    lines.append("")
    for _, row in growth_df.iterrows():
        lines.append(
            f"- **{row['branch']}**: score={row['potential_score']:.3f} "
            f"(rank {row['potential_rank']}) — {row.get('top_bundle_rule', 'no rule found')}"
        )

    lines += [
        "",
        "## How to Interpret",
        "",
        "- `beverage_attachment_rate`: proportion of orders containing at least one coffee/milkshake.",
        "- `beverage_gap_to_best`: percentage points below the top-performing branch.",
        "- `potential_score` (0-1): composite score weighting low attachment (35%),",
        "  large order volume (35%), and strong food→beverage association lift (30%).",
        "- `top_bundle_rule`: the single highest-lift food item that predicts a beverage purchase.",
        "",
        "## Recommended Actions",
        "",
        "1. Focus promotions on high-potential branches (score ≥ 0.5).",
        "2. Use the top bundle rule per branch to design combo offers",
        "   (e.g., 'Add a coffee for X% off when ordering [antecedent item]').",
        "3. Set branch KPI target: close 50% of the gap to best within one quarter.",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(data_dir: str, out_dir: str = None) -> None:
    """
    Execute the full Feature 5 pipeline.

    Parameters
    ----------
    data_dir : str
        Directory containing feat_branch_item.csv and
        transaction_baskets_basket_core.csv.
    out_dir : str, optional
        Output directory; defaults to <repo_root>/outputs/feature_5/.
    """
    _log.info("=== Feature 5: Coffee & Milkshake Growth Strategy ===")
    _log.info("Data dir: %s", data_dir)

    # 1. Load data
    branch_item_df, basket_df = load_all(data_dir)

    # 2. KPIs
    basket_kpis = compute_basket_kpis(basket_df)
    revenue_kpis = compute_revenue_kpis(branch_item_df)
    kpis_df = merge_kpis(basket_kpis, revenue_kpis)

    # 3. Association rules
    rules_df = compute_rules_by_branch(basket_df, min_support=0.005, min_confidence=0.03, top_k=10)

    # 4. Growth potential scoring
    growth_df = compute_growth_potential(kpis_df, rules_df)

    # 5. Outputs
    root = repo_root()
    output_dir = resolve_output_dir(root, "outputs/feature_5") if out_dir is None else Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _log.info("Writing outputs to %s", output_dir)

    kpis_df.to_csv(output_dir / "branch_beverage_kpis.csv", index=False)
    growth_df.to_csv(output_dir / "branch_growth_potential.csv", index=False)
    rules_df.to_csv(output_dir / "assoc_rules_by_branch.csv", index=False)

    rec = _build_recommendation(growth_df, rules_df)
    with open(output_dir / "recommendation.json", "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2, ensure_ascii=False)

    summary = _build_summary(kpis_df, growth_df, rules_df)
    with open(output_dir / "summary.md", "w", encoding="utf-8") as fh:
        fh.write(summary)

    # 6. Console summary
    print("\n" + "=" * 60)
    print("FEATURE 5 PIPELINE COMPLETE")
    print("=" * 60)
    print(f"\nOutputs written to: {output_dir}\n")
    print("Branch Beverage Attachment Rates:")
    print(
        kpis_df[["branch", "beverage_attachment_rate", "beverage_gap_to_best"]]
        .to_string(index=False)
    )
    print("\nGrowth Potential Ranking:")
    print(
        growth_df[["branch", "potential_score", "potential_rank"]]
        .to_string(index=False)
    )
    print("\nTop Global Association Rules (food → beverage):")
    global_rules = rules_df[rules_df["branch"] == "ALL"] if not rules_df.empty else pd.DataFrame()
    if not global_rules.empty:
        print(global_rules[["antecedents", "consequents", "lift"]].head(5).to_string(index=False))
    print("\n" + "=" * 60)

    # Invalidate cache so agent queries pick up fresh outputs
    clear_cache()


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

def run_smoke_tests() -> None:
    """Call all three agent query types and print results."""
    print("\n" + "=" * 60)
    print("SMOKE TESTS – Agent Interface")
    print("=" * 60)

    for qt in ["underperforming_branches", "highest_growth_potential", "beverage_gap"]:
        print(f"\n--- Query: {qt} ---")
        result = handle_query(qt, {})
        print(json.dumps(result, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("All smoke tests passed.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.feature_5.run",
        description="Feature 5 – Coffee & Milkshake Growth Strategy Pipeline",
    )
    parser.add_argument(
        "--data_dir",
        type=str,
        default="pipelines/output",
        help="Directory containing feat_branch_item.csv and transaction_baskets_basket_core.csv",
    )
    parser.add_argument(
        "--out_dir",
        type=str,
        default=None,
        help="Override output directory (default: <repo_root>/outputs/feature_5)",
    )
    parser.add_argument(
        "--smoke_test",
        action="store_true",
        help="Run agent smoke tests against existing outputs (skip pipeline execution)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)

    if args.smoke_test:
        run_smoke_tests()
        return

    # Resolve data_dir relative to cwd or repo root
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        # Try relative to repo root first, then cwd
        root_candidate = repo_root() / data_dir
        cwd_candidate = Path.cwd() / data_dir
        if root_candidate.exists():
            data_dir = root_candidate
        elif cwd_candidate.exists():
            data_dir = cwd_candidate
        # else: pass as-is and let loaders raise a useful error

    run_pipeline(str(data_dir), args.out_dir)


if __name__ == "__main__":
    main()
