"""
combo_queries.py
================
Business Objective #1 – Combo Optimization  |  Query Layer
Conut AI Engineering Hackathon

PURPOSE
-------
Provides four named query functions that translate business questions directly
into ranked DataFrames from the pre-computed combo_pairs.parquet artifact.

These functions are intentionally stateless and dependency-free (pandas only)
so that any agent, notebook, or API layer can import and call them without
touching the computation pipeline.

BUSINESS QUESTIONS COVERED
---------------------------
  Q1  top_combos_overall()       – "What are the top-performing combos overall?"
  Q2  top_combos_per_branch()    – "What are the top combos per branch?"
  Q3  top_combos_per_channel()   – "What are the top combos per channel?"
  Q4  combos_with_item()         – "What items strongly pair with X?"

CLI USAGE
---------
  # Q1 – top overall
  python combo_queries.py --question top_overall

  # Q2 – top per branch (all branches, or one specific)
  python combo_queries.py --question top_per_branch
  python combo_queries.py --question top_per_branch --branch "Conut Jnah"

  # Q3 – top per channel (all channels, or one specific)
  python combo_queries.py --question top_per_channel
  python combo_queries.py --question top_per_channel --channel DELIVERY

  # Q4 – strong pairs with a specific item
  python combo_queries.py --question pairs_with --item "CLASSIC CHIMNEY"

  All commands accept optional:
    --pairs_path   path/to/combo_pairs.parquet  (default: data/artifacts/combo_pairs.parquet)
    --top          N results per group           (default: 10)
    --rank_by      lift | support | count_ab     (default: lift)
    --min_count    minimum co-occurrence count   (default: per-question:
                   top_overall=5, top_per_branch=3, top_per_channel=5, pairs_with=3)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# ──────────────────────────────────────────────────────────────────────────────
# DEFAULT PATHS
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_PAIRS_PATH = Path(__file__).resolve().parents[2] / "data" / "artifacts" / "combo_pairs.parquet"

# ──────────────────────────────────────────────────────────────────────────────
# LOADER
# ──────────────────────────────────────────────────────────────────────────────

def load_pairs(path: str | Path = DEFAULT_PAIRS_PATH) -> pd.DataFrame:
    """Load combo_pairs.parquet. Raises FileNotFoundError with a helpful message."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"combo_pairs.parquet not found at: {p}\n"
            "Run combo_optimization.py first to generate it."
        )
    return pd.read_parquet(p)


# ──────────────────────────────────────────────────────────────────────────────
# HELPER
# ──────────────────────────────────────────────────────────────────────────────

_VALID_RANK = {"lift", "support", "count_ab"}


def _validate_rank(rank_by: str) -> str:
    if rank_by not in _VALID_RANK:
        raise ValueError(f"rank_by must be one of {_VALID_RANK}, got '{rank_by}'")
    return rank_by


def _display_cols(rank_by: str) -> list[str]:
    """Columns to surface in output, prioritising the ranking metric."""
    base = ["item_a", "item_b", "count_ab", "support", "confidence_ab",
            "confidence_ba", "lift", "n_orders"]
    if rank_by not in base:
        return base
    # Put rank_by column right after item pair for readability
    ordered = ["item_a", "item_b", rank_by] + [c for c in base if c != rank_by]
    # Remove duplicates while preserving order
    seen, result = set(), []
    for c in ordered:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Q1 – TOP COMBOS OVERALL
# ──────────────────────────────────────────────────────────────────────────────

def top_combos_overall(
    pairs_path: str | Path = DEFAULT_PAIRS_PATH,
    top:        int        = 10,
    rank_by:    str        = "lift",
    min_count:  int | None = None,   # None → use internal default of 5
) -> pd.DataFrame:
    """
    Q1: "What are the top-performing combos overall?"

    Returns the top N item pairs across ALL orders, ranked by `rank_by`.

    Parameters
    ----------
    top        : number of pairs to return
    rank_by    : "lift" | "support" | "count_ab"
    min_count  : only consider pairs with count_ab >= this value (default 5)

    Returns
    -------
    DataFrame with columns: item_a, item_b, <rank_by>, count_ab, support,
                            confidence_ab, confidence_ba, lift, n_orders
    """
    _validate_rank(rank_by)
    if min_count is None:
        min_count = 5
    df = load_pairs(pairs_path)
    result = (
        df[(df["scope"] == "overall") & (df["count_ab"] >= min_count)]
        .sort_values([rank_by, "count_ab"], ascending=[False, False])
        .head(top)
        [_display_cols(rank_by)]
        .reset_index(drop=True)
    )
    result.index += 1  # 1-based rank
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Q2 – TOP COMBOS PER BRANCH
# ──────────────────────────────────────────────────────────────────────────────

def top_combos_per_branch(
    pairs_path: str | Path = DEFAULT_PAIRS_PATH,
    branch:     str | None = None,
    top:        int        = 10,
    rank_by:    str        = "lift",
    min_count:  int | None = None,   # None → use internal default of 3
) -> pd.DataFrame:
    """
    Q2: "What are the top combos per branch?"

    Returns the top N item pairs for each branch (or a specific branch),
    with a 'branch' column and a per-branch rank column.

    Parameters
    ----------
    branch     : branch name string, e.g. "Conut Jnah". If None, returns all branches.
    top        : number of pairs per branch
    rank_by    : "lift" | "support" | "count_ab"
    min_count  : only consider pairs with count_ab >= this value (default 3;
                 kept low because small branches have fewer orders)
    """
    _validate_rank(rank_by)
    if min_count is None:
        min_count = 3
    df = load_pairs(pairs_path)

    # Select branch-level scopes only (not branch+channel)
    branch_df = df[df["scope"].str.match(r"^branch:[^|]+$") & (df["count_ab"] >= min_count)].copy()
    branch_df["branch"] = branch_df["scope"].str.replace("^branch:", "", regex=True)

    if branch is not None:
        branch_df = branch_df[branch_df["branch"] == branch]
        if branch_df.empty:
            available = df[df["scope"].str.match(r"^branch:[^|]+$")]["scope"] \
                          .str.replace("^branch:", "", regex=True).unique().tolist()
            raise ValueError(
                f"Branch '{branch}' not found in artifact.\n"
                f"Available branches: {available}"
            )

    cols = ["branch"] + _display_cols(rank_by)
    frames = []
    for br, grp in branch_df.groupby("branch"):
        top_grp = (
            grp.sort_values([rank_by, "count_ab"], ascending=[False, False])
            .head(top)[cols]
            .reset_index(drop=True)
        )
        top_grp.index += 1
        top_grp.index.name = "rank"
        frames.append(top_grp)

    return pd.concat(frames).reset_index() if frames else pd.DataFrame(columns=cols)


# ──────────────────────────────────────────────────────────────────────────────
# Q3 – TOP COMBOS PER CHANNEL
# ──────────────────────────────────────────────────────────────────────────────

def top_combos_per_channel(
    pairs_path: str | Path = DEFAULT_PAIRS_PATH,
    channel:    str | None = None,
    top:        int        = 10,
    rank_by:    str        = "lift",
    min_count:  int | None = None,   # None → use internal default of 5
) -> pd.DataFrame:
    """
    Q3: "What are the top combos per channel?"

    Returns the top N item pairs for each channel (DELIVERY / IN_STORE),
    or for a specific channel.

    Parameters
    ----------
    channel    : e.g. "DELIVERY" or "IN_STORE". If None, returns all channels.
    top        : number of pairs per channel
    rank_by    : "lift" | "support" | "count_ab"
    min_count  : only consider pairs with count_ab >= this value (default 5)
    """
    _validate_rank(rank_by)
    if min_count is None:
        min_count = 5
    df = load_pairs(pairs_path)

    ch_df = df[df["scope"].str.match(r"^channel:.+$") & (df["count_ab"] >= min_count)].copy()
    ch_df["channel"] = ch_df["scope"].str.replace("^channel:", "", regex=True)

    if channel is not None:
        ch_df = ch_df[ch_df["channel"] == channel.upper()]
        if ch_df.empty:
            available = df[df["scope"].str.match(r"^channel:.+$")]["scope"] \
                          .str.replace("^channel:", "", regex=True).unique().tolist()
            raise ValueError(
                f"Channel '{channel}' not found in artifact.\n"
                f"Available channels: {available}"
            )

    cols = ["channel"] + _display_cols(rank_by)
    frames = []
    for ch, grp in ch_df.groupby("channel"):
        top_grp = (
            grp.sort_values([rank_by, "count_ab"], ascending=[False, False])
            .head(top)[cols]
            .reset_index(drop=True)
        )
        top_grp.index += 1
        top_grp.index.name = "rank"
        frames.append(top_grp)

    return pd.concat(frames).reset_index() if frames else pd.DataFrame(columns=cols)


# ──────────────────────────────────────────────────────────────────────────────
# Q4 – COMBOS WITH ITEM X
# ──────────────────────────────────────────────────────────────────────────────

def combos_with_item(
    item:       str,
    pairs_path: str | Path = DEFAULT_PAIRS_PATH,
    scope:      str        = "overall",
    top:        int        = 10,
    rank_by:    str        = "lift",
    min_count:  int | None = None,   # None → use internal default of 3
) -> pd.DataFrame:
    """
    Q4: "What items strongly pair with X?"

    Returns all pairs in the artifact where either item_a or item_b matches
    `item` (case-insensitive substring match), ranked by `rank_by`.

    Parameters
    ----------
    item       : full or partial item name, e.g. "CLASSIC CHIMNEY" or "chimney"
    scope      : scope string to filter by (default "overall"); use "all" to
                 search across every scope
    top        : number of results to return
    rank_by    : "lift" | "support" | "count_ab"
    min_count  : only consider pairs with count_ab >= this value (default 3)
    """
    _validate_rank(rank_by)
    if min_count is None:
        min_count = 3
    df = load_pairs(pairs_path)

    if scope != "all":
        df = df[df["scope"] == scope]
        if df.empty and scope == "overall":
            raise ValueError("scope='overall' returned no data. Check the artifact.")

    item_upper = item.upper()
    mask = (
        df["item_a"].str.upper().str.contains(item_upper, regex=False) |
        df["item_b"].str.upper().str.contains(item_upper, regex=False)
    )
    result = df[mask & (df["count_ab"] >= min_count)].copy()

    if result.empty:
        # Try fuzzy hint
        all_items = pd.concat([df["item_a"], df["item_b"]]).str.upper().unique()
        hints = [i for i in all_items if item_upper[:4] in i][:5]
        hint_str = f"Did you mean one of: {hints}" if hints else "No similar items found."
        raise ValueError(
            f"No pairs found containing item '{item}' in scope '{scope}'.\n{hint_str}"
        )

    # Add a 'paired_with' column showing the other item from the pair
    result = result.copy()
    result["paired_with"] = result.apply(
        lambda r: r["item_b"]
        if item_upper in r["item_a"].upper()
        else r["item_a"],
        axis=1,
    )

    cols = ["scope", "paired_with"] + _display_cols(rank_by)
    result = (
        result
        .sort_values([rank_by, "count_ab"], ascending=[False, False])
        .head(top)[cols]
        .reset_index(drop=True)
    )
    result.index += 1
    return result


# ──────────────────────────────────────────────────────────────────────────────
# PRETTY PRINT HELPER
# ──────────────────────────────────────────────────────────────────────────────

def _print_result(df: pd.DataFrame, title: str) -> None:
    sep = "─" * 72
    print(f"\n{sep}")
    print(f"  {title}")
    print(sep)
    if df.empty:
        print("  (no results)")
    else:
        pd.set_option("display.max_colwidth", 32)
        pd.set_option("display.width", 120)
        pd.set_option("display.float_format", "{:.4f}".format)
        print(df.to_string())
    print(sep)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="combo_queries",
        description="Conut BO#1 – answer business combo questions from artifacts",
    )
    p.add_argument(
        "--question", required=True,
        choices=["top_overall", "top_per_branch", "top_per_channel", "pairs_with"],
        help="Which business question to answer",
    )
    p.add_argument(
        "--pairs_path", default=str(DEFAULT_PAIRS_PATH),
        help="Path to combo_pairs.parquet",
    )
    p.add_argument("--branch",  default=None, help="Specific branch name (Q2)")
    p.add_argument("--channel", default=None, help="Specific channel (Q3)")
    p.add_argument("--item",    default=None, help="Item name to query (Q4)")
    p.add_argument(
        "--scope", default="overall",
        help="Scope to search when using pairs_with (default: overall; use 'all' for all scopes)",
    )
    p.add_argument("--top",       type=int,   default=10,    help="Results per group (default: 10)")
    p.add_argument("--rank_by",   default="lift",
                   choices=["lift", "support", "count_ab"],  help="Ranking metric (default: lift)")
    p.add_argument(
        "--min_count", type=int, default=None, metavar="N",
        help=(
            "Override minimum co-occurrence count. "
            "Defaults per question: top_overall=5, top_per_branch=3, "
            "top_per_channel=5, pairs_with=3"
        ),
    )
    return p


def main(argv=None) -> None:
    args = _build_parser().parse_args(argv)
    # min_count is None unless the user explicitly passed --min_count N;
    # each function then applies its own sensible default.
    kw = dict(
        pairs_path=args.pairs_path,
        top=args.top,
        rank_by=args.rank_by,
        min_count=args.min_count,  # may be None → function uses its default
    )

    if args.question == "top_overall":
        result = top_combos_overall(**kw)
        _print_result(result, f"Q1 · Top {args.top} combos OVERALL  (ranked by {args.rank_by})")

    elif args.question == "top_per_branch":
        result = top_combos_per_branch(branch=args.branch, **kw)
        label = f"branch: {args.branch}" if args.branch else "ALL branches"
        _print_result(result, f"Q2 · Top {args.top} combos per branch  [{label}]  (ranked by {args.rank_by})")

    elif args.question == "top_per_channel":
        result = top_combos_per_channel(channel=args.channel, **kw)
        label = f"channel: {args.channel}" if args.channel else "ALL channels"
        _print_result(result, f"Q3 · Top {args.top} combos per channel  [{label}]  (ranked by {args.rank_by})")

    elif args.question == "pairs_with":
        if not args.item:
            print("ERROR: --item is required for question 'pairs_with'", file=sys.stderr)
            sys.exit(1)
        result = combos_with_item(item=args.item, scope=args.scope, **kw)
        _print_result(result, f"Q4 · Items strongly pairing with  \"{args.item}\"  (scope={args.scope}, ranked by {args.rank_by})")

    print()


if __name__ == "__main__":
    main()
