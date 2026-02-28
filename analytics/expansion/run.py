"""
run.py
======
Feature 3 – Expansion Feasibility  |  End-to-End Pipeline Entrypoint

EXAMPLE COMMAND:
    # From repo root (adjust path separator if on Windows):
    python -m pipelines.feature_3.run --data_dir "conut_bakery_scaled_data"

    # Explicit output directory:
    python -m pipelines.feature_3.run \\
        --data_dir "conut_bakery_scaled_data" \\
        --out_dir  "outputs/feature_3"

    # Re-run agent queries after pipeline completes:
    python -m pipelines.feature_3.run \\
        --data_dir "conut_bakery_scaled_data" \\
        --query expansion_recommendation

PIPELINE STAGES:
    1. Load & clean all source CSVs              (cleaning.load_all_sources)
    2. Compute raw KPIs per branch               (kpis.build_branch_kpis)
    3. Normalise & score KPIs                    (scoring.compute_feasibility_scores)
    4. Build geographic recommendation           (recommend.build_recommendation)
    5. Write outputs:
         branch_kpis.csv
         feasibility_scores.csv
         recommendation.json
         summary.md

OUTPUTS (default: outputs/feature_3/):
    branch_kpis.csv         – raw KPI table
    feasibility_scores.csv  – normalised scores + composite feasibility
    recommendation.json     – full structured recommendation
    summary.md              – human / agent-readable markdown summary
"""

# ──────────────────────────────────────────────────────────────────────────────
# EXAMPLE COMMAND (appears in --help too):
#   python -m pipelines.feature_3.run --data_dir "conut_bakery_scaled_data"
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from .cleaning import load_all_sources
from .kpis import build_branch_kpis
from .scoring import compute_feasibility_scores, WEIGHTS, WEIGHT_RATIONALE
from .recommend import build_recommendation
from .agent_interface import ClawbotExpansionInterface
from .utils import get_logger

logger = get_logger("feature_3.run")


# ──────────────────────────────────────────────────────────────────────────────
# OUTPUT WRITERS
# ──────────────────────────────────────────────────────────────────────────────

def _write_summary_md(
    recommendation: dict,
    feasibility_scores: pd.DataFrame,
    branch_kpis: pd.DataFrame,
    out_path: Path,
) -> None:
    """Generate a human-readable Markdown summary."""
    fs = feasibility_scores
    rec = recommendation

    lines = [
        "# Feature 3 – Expansion Feasibility Report",
        "",
        "## Recommendation",
        "",
        f"**Recommended Region:** {rec['recommended_region']}",
        f"**Candidate Locations:** {', '.join(rec['candidate_locations'])}",
        f"**Best Branch Profile to Replicate:** {rec['best_branch_to_replicate'].title()}",
        f"**Overall Feasibility Tier:** {rec['feasibility_tier']} ({rec['overall_feasibility']:.4f})",
        "",
        "### Reasoning",
        "",
    ]
    for r in rec["reasoning"]:
        lines.append(f"- {r}")
    lines.append("")

    if rec.get("warning"):
        lines += ["### ⚠️ Warning", "", rec["warning"], ""]

    lines += [
        "## Regional Scores",
        "",
        "| Region | Avg Feasibility Score |",
        "|--------|----------------------|",
    ]
    for region, score in sorted(rec["region_scores"].items(), key=lambda x: x[1], reverse=True):
        lines.append(f"| {region.title()} | {score:.4f} |")
    lines.append("")

    lines += [
        "## Branch Feasibility Scores",
        "",
        "| Rank | Branch | Score | Tier | Top Drivers |",
        "|------|--------|-------|------|-------------|",
    ]
    for i, row in fs.iterrows():
        lines.append(
            f"| {i+1} | {row['branch'].title()} | {row['feasibility_score']:.4f} "
            f"| {row['score_tier']} | {row.get('top_drivers', 'N/A')} |"
        )
    lines.append("")

    lines += [
        "## Growth Summary",
        "",
        "| Branch | Growth Rate | Direction | % Change (First→Last) |",
        "|--------|-------------|-----------|----------------------|",
    ]
    for branch, info in rec["growth_summary"].items():
        pct = f"{info['pct_change']*100:+.1f}%" if info.get("pct_change") is not None else "N/A"
        direction = "↑ Increasing" if info["is_growing"] else "↓ Declining/Flat"
        lines.append(
            f"| {branch.title()} | {info['growth_rate']:+.6f} | {direction} | {pct} |"
        )
    lines.append("")

    lines += [
        "## Score Weight Rationale",
        "",
        "| Component | Weight | Rationale |",
        "|-----------|--------|-----------|",
    ]
    for k, v in WEIGHT_RATIONALE.items():
        lines.append(f"| {k} | — | {v[:120]}{'...' if len(v) > 120 else ''} |")
    lines.append("")

    lines += [
        "## Key KPIs",
        "",
    ]
    kpi_cols = ["branch", "avg_monthly_revenue", "recent_growth_rate",
                "revenue_volatility", "avg_order_value", "delivery_share",
                "revenue_per_hour", "tax_burden"]
    kpi_cols = [c for c in kpi_cols if c in branch_kpis.columns]
    kpi_df = branch_kpis[kpi_cols]
    # Manual markdown table (no tabulate dependency)
    header = "| " + " | ".join(kpi_cols) + " |"
    sep    = "| " + " | ".join(["---"] * len(kpi_cols)) + " |"
    rows = []
    for _, r in kpi_df.iterrows():
        cells = []
        for c in kpi_cols:
            v = r[c]
            if isinstance(v, float):
                cells.append(f"{v:.4f}")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    lines += [header, sep] + rows
    lines += ["", "---", "_Generated by Feature 3 – Expansion Feasibility Pipeline_"]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote summary: %s", out_path)


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE RUNNER
# ──────────────────────────────────────────────────────────────────────────────

_PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_OUTPUT_DIR = _PACKAGE_DIR / "output"


def run_pipeline(
    data_dir: str | Path,
    out_dir:  str | Path | None = None,
) -> dict:
    """
    Execute the full Feature 3 pipeline.

    Returns
    -------
    dict with keys: branch_kpis, feasibility_scores, recommendation
    """
    data_dir = Path(data_dir)
    out_dir  = Path(out_dir) if out_dir is not None else _DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("Feature 3 – Expansion Feasibility Pipeline")
    logger.info("data_dir : %s", data_dir.resolve())
    logger.info("out_dir  : %s", out_dir.resolve())
    logger.info("=" * 60)

    # Stage 1: Load & clean ──────────────────────────────────────────────────
    logger.info("[1/4] Loading and cleaning source data …")
    sources = load_all_sources(data_dir)

    # Stage 2: KPIs ──────────────────────────────────────────────────────────
    logger.info("[2/4] Computing branch KPIs …")
    branch_kpis = build_branch_kpis(sources)

    # Stage 3: Score ─────────────────────────────────────────────────────────
    logger.info("[3/4] Normalising and scoring …")
    feasibility_scores = compute_feasibility_scores(branch_kpis)

    # Stage 4: Recommend ─────────────────────────────────────────────────────
    logger.info("[4/4] Building geographic recommendation …")
    recommendation = build_recommendation(feasibility_scores, branch_kpis)

    # Write outputs ──────────────────────────────────────────────────────────
    kpis_path   = out_dir / "branch_kpis.csv"
    scores_path = out_dir / "feasibility_scores.csv"
    rec_path    = out_dir / "recommendation.json"
    md_path     = out_dir / "summary.md"

    branch_kpis.to_csv(kpis_path, index=False)
    logger.info("Wrote: %s", kpis_path)

    feasibility_scores.to_csv(scores_path, index=False)
    logger.info("Wrote: %s", scores_path)

    with open(rec_path, "w", encoding="utf-8") as f:
        json.dump(recommendation, f, indent=2, ensure_ascii=False)
    logger.info("Wrote: %s", rec_path)

    _write_summary_md(recommendation, feasibility_scores, branch_kpis, md_path)

    logger.info("Pipeline complete. Outputs in: %s", out_dir.resolve())

    # Print quick summary to console ─────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  EXPANSION FEASIBILITY – RESULTS")
    print("=" * 60)
    print(f"  Recommended Region : {recommendation['recommended_region']}")
    print(f"  Candidate Locations: {', '.join(recommendation['candidate_locations'])}")
    print(f"  Best Branch Profile: {recommendation['best_branch_to_replicate'].title()}")
    print(f"  Feasibility Tier   : {recommendation['feasibility_tier']}")
    print()
    print("  Branch Scores:")
    for _, row in feasibility_scores.iterrows():
        gr = branch_kpis.loc[branch_kpis["branch"] == row["branch"], "recent_growth_rate"]
        gr_val = float(gr.iloc[0]) if not gr.empty else 0.0
        arrow = "↑" if gr_val > 0 else "↓"
        print(f"    {row['branch'].title():<16} {row['feasibility_score']:.4f}  "
              f"[{row['score_tier']}]  growth {arrow}{gr_val:+.4f}")
    print()
    print("  Reasoning:")
    for r in recommendation["reasoning"]:
        print(f"    • {r}")
    if recommendation.get("warning"):
        print(f"\n  ⚠  {recommendation['warning']}")
    print("=" * 60 + "\n")

    return {
        "branch_kpis":        branch_kpis,
        "feasibility_scores": feasibility_scores,
        "recommendation":     recommendation,
    }


# ──────────────────────────────────────────────────────────────────────────────
# AGENT QUERY MODE
# ──────────────────────────────────────────────────────────────────────────────

def run_query(out_dir: str | Path, query_type: str, branch: str | None = None) -> None:
    """Run a single agent query against pre-computed outputs and print result."""
    agent = ClawbotExpansionInterface.from_outputs(out_dir)
    payload = {"branch": branch} if branch else {}
    result  = agent.handle_query(query_type, payload)
    print(json.dumps(result, indent=2, ensure_ascii=False))


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m analytics.expansion.run",
        description=(
            "Feature 3 – Expansion Feasibility Pipeline\n\n"
            "Run the full pipeline:\n"
            "  python -m analytics.expansion.run --data_dir conut_bakery_scaled_data\n\n"
            "Run an agent query (requires prior pipeline run):\n"
            "  python -m pipelines.feature_3.run --query expansion_recommendation\n"
            "  python -m pipelines.feature_3.run --query feasibility_explanation --branch tyre\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--data_dir", default="conut_bakery_scaled_data",
        help="Directory containing raw Conut CSV exports (default: conut_bakery_scaled_data)",
    )
    p.add_argument(
        "--out_dir", default=None,
        help="Output directory for CSVs, JSON, and Markdown (default: analytics/expansion/output/)",
    )
    p.add_argument(
        "--query",
        choices=[
            "expansion_recommendation", "branch_ranking",
            "growth_summary", "feasibility_explanation", "risk_summary",
        ],
        default=None,
        help="Run a single agent query against pre-computed outputs (skips pipeline)",
    )
    p.add_argument(
        "--branch", default=None,
        help="Branch filter for feasibility_explanation query (e.g. 'tyre')",
    )
    p.add_argument(
        "--log_level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    # Configure log level
    logging.getLogger("feature_3").setLevel(getattr(logging, args.log_level))

    if args.query:
        # Query-only mode: read pre-computed outputs
        query_dir = args.out_dir if args.out_dir else str(_DEFAULT_OUTPUT_DIR)
        run_query(query_dir, args.query, branch=args.branch)
    else:
        # Full pipeline
        run_pipeline(data_dir=args.data_dir, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
