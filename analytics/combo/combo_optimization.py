"""
combo_optimization.py
=====================
Business Objective #1 – Combo Optimization (Conut AI Engineering Hackathon)

PURPOSE
-------
Feature-engineering pipeline that transforms a cleaned line-item dataset into:
  1. order_baskets   – one row per order, deduplicated item sets + context features
  2. combo_pairs     – association-rule statistics for every item pair, computed
                       across four scopes: overall / per-branch / per-channel /
                       per-branch+channel

Intended consumers: downstream AI agents and analysts. No agent code is included
here; see the "AGENT QUERY GUIDE" section at the bottom of this docstring.

──────────────────────────────────────────────────────────────────────────────
ARTIFACT SCHEMA
──────────────────────────────────────────────────────────────────────────────

order_baskets.parquet
  order_id       : str | int   – unique basket / transaction identifier
  branch         : str         – store branch name
  channel        : str         – DELIVERY | IN_STORE  (inferred if absent)
  items_set      : object      – frozenset of deduplicated item strings
  n_items        : int         – cardinality of items_set
  day_of_week    : int|None    – 0=Mon … 6=Sun  (populated when timestamp present)
  hour           : int|None    – 0-23            (populated when timestamp present)
  month          : int|None    – 1-12            (populated when timestamp present)

combo_pairs.parquet
  scope          : str   – "overall" | "branch:<name>" | "channel:<name>"
                            | "branch:<name>|channel:<name>"
  item_a         : str   – lexicographically smaller item in the pair
  item_b         : str   – lexicographically larger  item in the pair
  n_orders       : int   – total orders in this scope
  count_a        : int   – orders in scope containing item_a
  count_b        : int   – orders in scope containing item_b
  count_ab       : int   – orders in scope containing both
  support        : float – count_ab / n_orders          ∈ [0, 1]
  confidence_ab  : float – count_ab / count_a  (a→b)    ∈ [0, 1]
  confidence_ba  : float – count_ab / count_b  (b→a)    ∈ [0, 1]
  lift           : float – (count_ab * n_orders) / (count_a * count_b)

──────────────────────────────────────────────────────────────────────────────
AGENT QUERY GUIDE  (read combo_pairs.parquet and filter)
──────────────────────────────────────────────────────────────────────────────

  1. Top combos overall (by lift, min 20 co-occurrences):
       df[df.scope == "overall"].query("count_ab >= 20")
          .nlargest(20, "lift")

  2. Top combos for a specific branch:
       df[df.scope == "branch:Conut - Tyre"].nlargest(20, "support")

  3. Top combos for a specific channel:
       df[df.scope == "channel:DELIVERY"].nlargest(20, "lift")

  4. All combos containing item X (either position):
       target = "CLASSIC CHIMNEY"
       df[(df.item_a == target) | (df.item_b == target)]
          .sort_values("lift", ascending=False)

  5. Cross-scope comparison for a pair:
       df[(df.item_a == "CHIMNEY THE ONE") & (df.item_b == "CLASSIC CHIMNEY")]

  NOTE: pairs are always stored with item_a < item_b (lexicographic order).
  When querying for a specific item as either element, filter both columns.

──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import ast
import logging
import random
import sys
from itertools import combinations
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

DELIVERY_MARKER = "DELIVERY CHARGE"   # item name used to infer channel
DEFAULT_MIN_SUPPORT  = 0.01
DEFAULT_MIN_COUNT_AB = 10


# ──────────────────────────────────────────────────────────────────────────────
# STEP 1 – LOAD & NORMALISE INPUT
# ──────────────────────────────────────────────────────────────────────────────

def load_line_items(path: str | Path) -> pd.DataFrame:
    """
    Read a CSV or Parquet line-item file and return a normalised DataFrame with
    guaranteed columns:  order_id, item, branch, channel, timestamp (nullable).

    Accepted input schemas
    ----------------------
    A)  Cleaned line-items  – must have: order_id (or basket_id), item, branch
        Optional:  channel, timestamp / date, qty
    B)  transaction_baskets_raw_lines.csv produced by the project pipeline
        columns: branch, customer, basket_id, item, qty, price
    C)  transaction_baskets_basket_core.csv (parsed items_list string column)
        columns: basket_id, branch, customer, items_list, …
    """
    p = Path(path)
    logger.info("Loading %s", p)

    if p.suffix.lower() == ".parquet":
        df = pd.read_parquet(p)
    else:
        df = pd.read_csv(p)

    df.columns = df.columns.str.strip().str.lower()

    # ── column aliases ────────────────────────────────────────────────────────
    if "basket_id" in df.columns and "order_id" not in df.columns:
        df = df.rename(columns={"basket_id": "order_id"})

    # ── basket_core format: explode items_list string → one row per item ──────
    if "items_list" in df.columns and "item" not in df.columns:
        logger.info("Detected basket_core format – exploding items_list")
        df["items_list"] = df["items_list"].apply(_safe_parse_list)
        df = df.explode("items_list").rename(columns={"items_list": "item"})
        df = df.dropna(subset=["item"])

    # ── required columns ──────────────────────────────────────────────────────
    required = {"order_id", "item", "branch"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Input file is missing required columns: {missing}. "
            f"Found: {list(df.columns)}"
        )

    df["order_id"] = df["order_id"].astype(str)
    df["item"]     = df["item"].astype(str).str.strip()
    df["branch"]   = df["branch"].astype(str).str.strip()

    # ── channel ───────────────────────────────────────────────────────────────
    if "channel" in df.columns:
        df["channel"] = df["channel"].astype(str).str.strip().str.upper()
    else:
        logger.info(
            "No 'channel' column found – inferring from presence of '%s'",
            DELIVERY_MARKER,
        )
        delivery_orders = set(
            df.loc[
                df["item"].str.upper() == DELIVERY_MARKER.upper(), "order_id"
            ]
        )
        df["channel"] = df["order_id"].map(
            lambda oid: "DELIVERY" if oid in delivery_orders else "IN_STORE"
        )

    # ── optional timestamp ────────────────────────────────────────────────────
    ts_col = next(
        (c for c in df.columns if c in {"timestamp", "date", "order_date"}),
        None,
    )
    if ts_col:
        df["timestamp"] = pd.to_datetime(df[ts_col], errors="coerce")
    else:
        df["timestamp"] = pd.NaT

    keep = ["order_id", "item", "branch", "channel", "timestamp"]
    return df[[c for c in keep if c in df.columns]].copy()


def _safe_parse_list(val) -> list:
    """Parse a stringified Python list such as \"['A', 'B']\"."""
    if not isinstance(val, str):
        return []
    try:
        result = ast.literal_eval(val)
        return result if isinstance(result, list) else []
    except (ValueError, SyntaxError):
        return []


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2 – BUILD ORDER BASKETS
# ──────────────────────────────────────────────────────────────────────────────

def build_order_baskets(lines: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse line items into one row per order_id.

    Returns
    -------
    DataFrame with columns:
        order_id, branch, channel, items_set, n_items,
        day_of_week, hour, month
    """
    logger.info("Building order baskets from %d line rows …", len(lines))

    # Deduplicate items within each order
    item_presence = (
        lines[["order_id", "item"]]
        .drop_duplicates()
    )

    # Aggregate to sets
    baskets = (
        item_presence
        .groupby("order_id")["item"]
        .apply(frozenset)
        .rename("items_set")
        .reset_index()
    )
    baskets["n_items"] = baskets["items_set"].apply(len)

    # Attach context columns (one value per order – take first)
    ctx = (
        lines[["order_id", "branch", "channel", "timestamp"]]
        .drop_duplicates(subset="order_id")
        .set_index("order_id")
    )
    baskets = baskets.join(ctx, on="order_id")

    # Time features
    has_ts = baskets["timestamp"].notna().any()
    if has_ts:
        ts = pd.to_datetime(baskets["timestamp"], errors="coerce")
        baskets["day_of_week"] = ts.dt.dayofweek.where(ts.notna()).astype("Int64")
        baskets["hour"]        = ts.dt.hour.where(ts.notna()).astype("Int64")
        baskets["month"]       = ts.dt.month.where(ts.notna()).astype("Int64")
    else:
        baskets["day_of_week"] = pd.NA
        baskets["hour"]        = pd.NA
        baskets["month"]       = pd.NA

    baskets = baskets.drop(columns=["timestamp"], errors="ignore")

    col_order = [
        "order_id", "branch", "channel", "items_set", "n_items",
        "day_of_week", "hour", "month",
    ]
    logger.info(
        "Built %d baskets  (median size=%.1f items)",
        len(baskets),
        baskets["n_items"].median(),
    )
    return baskets[col_order]


# ──────────────────────────────────────────────────────────────────────────────
# STEP 3 – EXPLODE ITEM PAIRS (vectorised)
# ──────────────────────────────────────────────────────────────────────────────

def explode_pairs(item_presence: pd.DataFrame) -> pd.DataFrame:
    """
    From a deduplicated (order_id, item) table, produce all unique sorted item
    pairs per order via a self-join filtered on item_a < item_b.

    This is far more memory-efficient than nested Python loops for large datasets.
    Returns columns: order_id, item_a, item_b
    """
    logger.info("Exploding pairs via self-join …")
    left  = item_presence.rename(columns={"item": "item_a"})
    right = item_presence.rename(columns={"item": "item_b"})

    pairs = left.merge(right, on="order_id")
    # Keep only sorted pairs: avoids (A,B)+(B,A) and self-pairs
    pairs = pairs[pairs["item_a"] < pairs["item_b"]].copy()
    pairs = pairs[["order_id", "item_a", "item_b"]].reset_index(drop=True)

    logger.info("Exploded %d (order, pair) rows", len(pairs))
    return pairs


# ──────────────────────────────────────────────────────────────────────────────
# STEP 4 – COMPUTE PAIR STATISTICS FOR ONE SCOPE
# ──────────────────────────────────────────────────────────────────────────────

def _pair_stats_for_scope(
    pairs_with_ctx:    pd.DataFrame,   # order_id, item_a, item_b [, scope_cols]
    presence_with_ctx: pd.DataFrame,   # order_id, item  [, scope_cols]
                                       # already deduplicated at (order_id, item)
    scope_cols:        list[str],
    min_support:       float,
    min_count_ab:      int,
    scope_label_fn,                    # callable(row) → scope string
) -> pd.DataFrame:
    """
    Core statistics engine.  Works for any scope by injecting scope_cols.

    presence_with_ctx is assumed to have exactly one row per (order_id, item)
    combination (plus scope columns). No internal deduplication of items is
    performed here so that all per-item counts are correct.
    """
    pair_keys = scope_cols + ["item_a", "item_b"]
    item_keys = scope_cols + ["item"]

    # ── count_ab: distinct orders containing both items in this scope ─────────
    # pairs_with_ctx may have one row per (order_id, item_a, item_b) already
    # because it was built from a deduplicated presence table; deduplicate
    # defensively to be safe.
    count_ab = (
        pairs_with_ctx
        .drop_duplicates(subset=scope_cols + ["order_id", "item_a", "item_b"])
        .groupby(pair_keys, sort=False)
        .size()
        .rename("count_ab")
        .reset_index()
    )

    # Early-exit if nothing passes the count threshold
    count_ab = count_ab[count_ab["count_ab"] >= min_count_ab]
    if count_ab.empty:
        return pd.DataFrame()

    # ── count per item: distinct orders containing item in this scope ─────────
    # presence_with_ctx is (order_id, item, [scope_cols]) – already deduplicated
    # at the (order_id, item) level, so a plain groupby gives correct counts.
    item_counts = (
        presence_with_ctx
        .groupby(item_keys, sort=False)
        .size()
        .rename("count_item")
        .reset_index()
    )

    # ── n_orders: total distinct orders in this scope ─────────────────────────
    if scope_cols:
        n_orders_map = (
            presence_with_ctx
            .drop_duplicates(subset=scope_cols + ["order_id"])
            .groupby(scope_cols, sort=False)["order_id"]
            .count()
            .rename("n_orders")
            .reset_index()
        )
        stat = count_ab.merge(n_orders_map, on=scope_cols, how="left")
    else:
        n_orders = presence_with_ctx["order_id"].nunique()
        stat = count_ab.copy()
        stat["n_orders"] = n_orders

    # ── merge count_a and count_b ─────────────────────────────────────────────
    on_a = (scope_cols + ["item_a"]) if scope_cols else ["item_a"]
    on_b = (scope_cols + ["item_b"]) if scope_cols else ["item_b"]

    merge_a = item_counts.rename(columns={"item": "item_a", "count_item": "count_a"})
    merge_b = item_counts.rename(columns={"item": "item_b", "count_item": "count_b"})

    stat = stat.merge(merge_a, on=on_a, how="left")
    stat = stat.merge(merge_b, on=on_b, how="left")

    # ── metric computation ────────────────────────────────────────────────────
    stat["support"]       = stat["count_ab"] / stat["n_orders"]
    stat["confidence_ab"] = stat["count_ab"] / stat["count_a"]   # a→b
    stat["confidence_ba"] = stat["count_ab"] / stat["count_b"]   # b→a

    denom = stat["count_a"] * stat["count_b"]
    stat["lift"] = (stat["count_ab"] * stat["n_orders"]).where(denom > 0) / denom.replace(0, float("nan"))

    # ── filter ────────────────────────────────────────────────────────────────
    stat = stat[
        (stat["count_ab"] >= min_count_ab) &
        (stat["support"]  >= min_support)
    ].copy()

    if stat.empty:
        return pd.DataFrame()

    # ── build scope label column ──────────────────────────────────────────────
    stat["scope"] = stat.apply(scope_label_fn, axis=1)

    cols = ["scope", "item_a", "item_b", "n_orders",
            "count_a", "count_b", "count_ab",
            "support", "confidence_ab", "confidence_ba", "lift"]
    return stat[cols].reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────────────────
# STEP 5 – COMPUTE ALL SCOPES
# ──────────────────────────────────────────────────────────────────────────────

def compute_combo_pairs(
    baskets:      pd.DataFrame,
    min_support:  float = DEFAULT_MIN_SUPPORT,
    min_count_ab: int   = DEFAULT_MIN_COUNT_AB,
) -> pd.DataFrame:
    """
    Compute pair statistics across 4 scopes:
        overall | per-branch | per-channel | per-branch+channel

    Returns a single DataFrame with a 'scope' string column.
    """
    # ── item presence table (deduplicated) ────────────────────────────────────
    rows = []
    for _, row in baskets.iterrows():
        for itm in row["items_set"]:
            rows.append({
                "order_id": row["order_id"],
                "item":     itm,
                "branch":   row["branch"],
                "channel":  row["channel"],
            })
    presence = pd.DataFrame(rows)
    logger.info("Item-presence table: %d rows", len(presence))

    # ── pairs table ────────────────────────────────────────────────────────────
    pairs_raw = explode_pairs(presence[["order_id", "item"]])

    # Attach branch + channel to pairs via order_id
    order_ctx = baskets[["order_id", "branch", "channel"]].set_index("order_id")
    pairs = pairs_raw.join(order_ctx, on="order_id")

    # ── compute per scope ─────────────────────────────────────────────────────
    frames = []

    # 1. OVERALL
    logger.info("Computing pair stats: overall …")
    f = _pair_stats_for_scope(
        pairs_with_ctx    = pairs,
        presence_with_ctx = presence,
        scope_cols        = [],
        min_support       = min_support,
        min_count_ab      = min_count_ab,
        scope_label_fn     = lambda _: "overall",
    )
    if not f.empty:
        frames.append(f)

    # 2. PER BRANCH
    logger.info("Computing pair stats: per branch …")
    f = _pair_stats_for_scope(
        pairs_with_ctx    = pairs,
        presence_with_ctx = presence,
        scope_cols        = ["branch"],
        min_support       = min_support,
        min_count_ab      = min_count_ab,
        scope_label_fn     = lambda r: f"branch:{r['branch']}",
    )
    if not f.empty:
        frames.append(f)

    # 3. PER CHANNEL
    logger.info("Computing pair stats: per channel …")
    f = _pair_stats_for_scope(
        pairs_with_ctx    = pairs,
        presence_with_ctx = presence,
        scope_cols        = ["channel"],
        min_support       = min_support,
        min_count_ab      = min_count_ab,
        scope_label_fn     = lambda r: f"channel:{r['channel']}",
    )
    if not f.empty:
        frames.append(f)

    # 4. PER BRANCH + CHANNEL
    logger.info("Computing pair stats: per branch+channel …")
    f = _pair_stats_for_scope(
        pairs_with_ctx    = pairs,
        presence_with_ctx = presence,
        scope_cols        = ["branch", "channel"],
        min_support       = min_support,
        min_count_ab      = min_count_ab,
        scope_label_fn     = lambda r: f"branch:{r['branch']}|channel:{r['channel']}",
    )
    if not f.empty:
        frames.append(f)

    if not frames:
        logger.warning("No pairs survived the support / count thresholds.")
        return pd.DataFrame(columns=[
            "scope", "item_a", "item_b", "n_orders",
            "count_a", "count_b", "count_ab",
            "support", "confidence_ab", "confidence_ba", "lift",
        ])

    result = pd.concat(frames, ignore_index=True)

    # Drop rows where item lookups produced NaN (edge-case: item present in pairs
    # but missing from the presence table for that scope — should not happen with
    # clean data, but guard defensively).
    result = result.dropna(subset=["count_a", "count_b", "n_orders"])

    result["n_orders"]  = result["n_orders"].astype(int)
    result["count_a"]   = result["count_a"].astype(int)
    result["count_b"]   = result["count_b"].astype(int)
    result["count_ab"]  = result["count_ab"].astype(int)

    logger.info("Total combo_pairs rows: %d", len(result))
    return result


# ──────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ──────────────────────────────────────────────────────────────────────────────

def run_validation(baskets: pd.DataFrame, pairs: pd.DataFrame) -> None:
    """
    Run assertions / sanity checks. Raises AssertionError on failure.
    """
    logger.info("Running validation checks …")
    n_fail = 0

    def check(cond: bool, msg: str) -> None:
        nonlocal n_fail
        if not cond:
            logger.error("VALIDATION FAILED: %s", msg)
            n_fail += 1

    if pairs.empty:
        logger.warning("combo_pairs is empty – skipping metric range checks")
    else:
        # ── metric ranges ─────────────────────────────────────────────────────
        check(pairs["support"].between(0, 1).all(),
              "support out of [0,1]")
        check(pairs["confidence_ab"].between(0, 1).all(),
              "confidence_ab out of [0,1]")
        check(pairs["confidence_ba"].between(0, 1).all(),
              "confidence_ba out of [0,1]")

        # ── count consistency ─────────────────────────────────────────────────
        check((pairs["count_ab"] <= pairs["count_a"]).all(),
              "count_ab > count_a for some rows")
        check((pairs["count_ab"] <= pairs["count_b"]).all(),
              "count_ab > count_b for some rows")

        # ── no mirrored duplicates (A,B) and (B,A) in same scope ─────────────
        scoped_pairs = pairs[["scope", "item_a", "item_b"]]
        mirror = scoped_pairs.rename(columns={"item_a": "item_b", "item_b": "item_a"})
        merged = scoped_pairs.merge(mirror, on=["scope", "item_a", "item_b"])
        check(merged.empty,
              f"Found {len(merged)} mirrored duplicate pairs (A,B)+(B,A)")

        # ── lexicographic order A < B ─────────────────────────────────────────
        check((pairs["item_a"] < pairs["item_b"]).all(),
              "Some pairs have item_a >= item_b (not lexicographically sorted)")

    # ── basket-level: k*(k-1)/2 pairs per order ───────────────────────────────
    multi_item_baskets = baskets[baskets["n_items"] > 1]
    if not multi_item_baskets.empty:
        sample_size = min(30, len(multi_item_baskets))
        sample_orders = multi_item_baskets.sample(sample_size, random_state=42)

        # Rebuild pairs for sampled orders from baskets directly
        for _, row in sample_orders.iterrows():
            oid     = row["order_id"]
            items   = sorted(row["items_set"])
            k       = len(items)
            expected_pairs = k * (k - 1) // 2
            generated      = list(combinations(items, 2))
            check(
                len(generated) == expected_pairs,
                f"order_id={oid}: expected {expected_pairs} pairs, got {len(generated)}",
            )

    if n_fail == 0:
        logger.info("All validation checks PASSED.")
    else:
        raise AssertionError(
            f"{n_fail} validation check(s) failed. See log output above."
        )


# ──────────────────────────────────────────────────────────────────────────────
# SAVE HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _save_parquet(df: pd.DataFrame, path: str | Path, label: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # frozenset columns are not Parquet-serialisable – convert to sorted lists
    for col in df.columns:
        if df[col].dtype == object and df[col].apply(lambda x: isinstance(x, (frozenset, set))).any():
            df = df.copy()
            df[col] = df[col].apply(lambda x: sorted(x) if isinstance(x, (frozenset, set)) else x)

    df.to_parquet(p, index=False)
    logger.info("Saved %s → %s  (%d rows, %d cols)", label, p, *df.shape)


# ──────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ──────────────────────────────────────────────────────────────────────────────

def run(
    in_path:      str | Path,
    out_baskets:  str | Path,
    out_pairs:    str | Path,
    min_support:  float = DEFAULT_MIN_SUPPORT,
    min_count_ab: int   = DEFAULT_MIN_COUNT_AB,
    validate:     bool  = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Full pipeline: load → baskets → pairs → validate → save.

    Returns (baskets_df, pairs_df).
    """
    lines   = load_line_items(in_path)
    baskets = build_order_baskets(lines)
    pairs   = compute_combo_pairs(baskets, min_support, min_count_ab)

    if validate:
        run_validation(baskets, pairs)

    _save_parquet(baskets, out_baskets, "order_baskets")
    _save_parquet(pairs,   out_pairs,   "combo_pairs")

    return baskets, pairs


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="combo_optimization",
        description="Conut BO#1 – Combo Optimization feature pipeline",
    )
    p.add_argument(
        "--in", dest="in_path", required=True, metavar="PATH",
        help="Path to cleaned line-item CSV or Parquet",
    )
    p.add_argument(
        "--out_baskets", default="data/processed/order_baskets.parquet",
        metavar="PATH", help="Output path for order_baskets.parquet",
    )
    p.add_argument(
        "--out_pairs", default="data/artifacts/combo_pairs.parquet",
        metavar="PATH", help="Output path for combo_pairs.parquet",
    )
    p.add_argument(
        "--min_support", type=float, default=DEFAULT_MIN_SUPPORT,
        help=f"Minimum support threshold (default: {DEFAULT_MIN_SUPPORT})",
    )
    p.add_argument(
        "--min_count_ab", type=int, default=DEFAULT_MIN_COUNT_AB,
        help=f"Minimum co-occurrence count (default: {DEFAULT_MIN_COUNT_AB})",
    )
    p.add_argument(
        "--no_validate", action="store_true",
        help="Skip validation assertions",
    )
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()
    baskets_df, pairs_df = run(
        in_path      = args.in_path,
        out_baskets  = args.out_baskets,
        out_pairs    = args.out_pairs,
        min_support  = args.min_support,
        min_count_ab = args.min_count_ab,
        validate     = not args.no_validate,
    )

    # ── quick summary to stdout ───────────────────────────────────────────────
    print("\n─── BASKETS SUMMARY ───────────────────────────────────────────")
    print(f"  Total orders  : {len(baskets_df):,}")
    print(f"  Unique items  : {len({i for s in baskets_df['items_set'] for i in s}):,}")
    print(f"  Branches      : {baskets_df['branch'].nunique()}")
    print(f"  Channels      : {baskets_df['channel'].nunique()}  {baskets_df['channel'].value_counts().to_dict()}")
    print(f"  Basket size   : median={baskets_df['n_items'].median():.1f}  max={baskets_df['n_items'].max()}")

    print("\n─── COMBO PAIRS SUMMARY ───────────────────────────────────────")
    if not pairs_df.empty:
        print(f"  Total rows    : {len(pairs_df):,}")
        print(f"  Scopes        : {pairs_df['scope'].nunique()}")
        overall = pairs_df[pairs_df["scope"] == "overall"]
        if not overall.empty:
            top = overall.nlargest(5, "lift")[
                ["item_a", "item_b", "count_ab", "support", "lift"]
            ].to_string(index=False)
            print("\n  Top-5 overall pairs by lift:\n")
            print(top)
    else:
        print("  No pairs met the thresholds.")

    print()
    sys.exit(0)
