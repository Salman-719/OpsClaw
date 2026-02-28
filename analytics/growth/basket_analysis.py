"""
basket_analysis.py – Market-basket association rules focusing on beverages.

Uses mlxtend.frequent_patterns (apriori + association_rules) when available.
Falls back to a counting-based lift computation for antecedent→beverage pairs.

Outputs per-branch association rules (antecedents → beverage RHS) plus
global rules across all branches.
"""
from __future__ import annotations

import itertools
from collections import Counter
from typing import Dict, List, Optional

import pandas as pd

from .beverage_detection import is_target_beverage
from .parsing import parse_items_list
from .utils import get_logger

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _try_import_mlxtend():
    try:
        from mlxtend.frequent_patterns import apriori, association_rules
        from mlxtend.preprocessing import TransactionEncoder
        return apriori, association_rules, TransactionEncoder
    except ImportError:
        return None, None, None


def _build_transactions(basket_df: pd.DataFrame) -> List[List[str]]:
    """Extract list-of-items for every basket."""
    return basket_df["items_list"].apply(parse_items_list).tolist()


# ---------------------------------------------------------------------------
# mlxtend path
# ---------------------------------------------------------------------------

def _rules_mlxtend(
    transactions: List[List[str]],
    min_support: float = 0.01,
    min_confidence: float = 0.05,
    top_k: int = 10,
) -> pd.DataFrame:
    apriori_fn, assoc_fn, TransactionEncoder = _try_import_mlxtend()
    if apriori_fn is None:
        return pd.DataFrame()

    te = TransactionEncoder()
    te_array = te.fit_transform(transactions)
    df_enc = pd.DataFrame(te_array, columns=te.columns_)

    # Guard: apriori needs enough items & transactions
    if df_enc.shape[0] < 5 or df_enc.shape[1] < 2:
        _log.warning("Too few transactions/items for apriori; skipping mlxtend path.")
        return pd.DataFrame()

    frequent = apriori_fn(
        df_enc, min_support=min_support, use_colnames=True, low_memory=True
    )
    if frequent.empty:
        _log.warning("No frequent itemsets found (min_support=%.3f).", min_support)
        return pd.DataFrame()

    rules = assoc_fn(frequent, metric="confidence", min_threshold=min_confidence)
    if rules.empty:
        return pd.DataFrame()

    # Keep only rules where ALL consequents are beverages
    rules = rules[
        rules["consequents"].apply(
            lambda cs: all(is_target_beverage(c) for c in cs)
        )
    ].copy()

    # Format for output
    rules["antecedents_str"] = rules["antecedents"].apply(
        lambda x: ", ".join(sorted(x))
    )
    rules["consequents_str"] = rules["consequents"].apply(
        lambda x: ", ".join(sorted(x))
    )
    rules = rules.sort_values("lift", ascending=False).head(top_k)
    return rules[["antecedents_str", "consequents_str", "support", "confidence", "lift"]].rename(
        columns={"antecedents_str": "antecedents", "consequents_str": "consequents"}
    )


# ---------------------------------------------------------------------------
# Fallback: counting-based lift for (single food item → beverage) pairs
# ---------------------------------------------------------------------------

def _rules_counting(
    transactions: List[List[str]],
    top_k: int = 10,
) -> pd.DataFrame:
    """
    Compute support / confidence / lift for
    (non-beverage item → target beverage) pairs.

    Only considers single-item antecedents for simplicity.
    """
    n = len(transactions)
    if n == 0:
        return pd.DataFrame()

    item_count: Counter = Counter()
    bev_count: Counter = Counter()
    pair_count: Counter = Counter()

    for items in transactions:
        unique = list(set(items))
        beverages = [i for i in unique if is_target_beverage(i)]
        non_bev = [i for i in unique if not is_target_beverage(i)]
        for item in unique:
            item_count[item] += 1
        for bev in beverages:
            bev_count[bev] += 1
        # Pairs: non_bev food → beverage
        for food in non_bev:
            for bev in beverages:
                pair_count[(food, bev)] += 1

    rows = []
    for (food, bev), count in pair_count.items():
        support = count / n
        food_sup = item_count[food] / n
        bev_sup = bev_count[bev] / n
        confidence = count / item_count[food] if item_count[food] > 0 else 0.0
        lift = confidence / bev_sup if bev_sup > 0 else 0.0
        rows.append(
            {
                "antecedents": food,
                "consequents": bev,
                "support": round(support, 5),
                "confidence": round(confidence, 4),
                "lift": round(lift, 4),
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values("lift", ascending=False).head(top_k)
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_association_rules(
    basket_df: pd.DataFrame,
    min_support: float = 0.01,
    min_confidence: float = 0.05,
    top_k: int = 10,
) -> pd.DataFrame:
    """
    Compute beverage association rules for a (sub)set of baskets.

    Tries mlxtend first; falls back to counting-based approach.

    Parameters
    ----------
    basket_df : pd.DataFrame
        Subset of transaction_baskets_basket_core for one branch (or all).
    min_support, min_confidence : float
        mlxtend thresholds (ignored in fallback mode).
    top_k : int
        Maximum rules to return.

    Returns
    -------
    pd.DataFrame
        Columns: antecedents, consequents, support, confidence, lift.
    """
    transactions = _build_transactions(basket_df)
    _log.debug("Running association rules on %d transactions.", len(transactions))

    apriori_fn, _, _ = _try_import_mlxtend()
    if apriori_fn is not None:
        result = _rules_mlxtend(transactions, min_support, min_confidence, top_k)
        if not result.empty:
            return result
        _log.info("mlxtend returned no rules; falling back to counting-based approach.")

    return _rules_counting(transactions, top_k=top_k)


def compute_rules_by_branch(
    basket_df: pd.DataFrame,
    min_support: float = 0.01,
    min_confidence: float = 0.05,
    top_k: int = 10,
) -> pd.DataFrame:
    """
    Compute association rules per branch + globally.

    Returns
    -------
    pd.DataFrame
        Columns: branch, antecedents, consequents, support, confidence, lift.
        ``branch == "ALL"`` rows are the global rules.
    """
    _log.info("Computing association rules by branch …")
    all_rules: List[pd.DataFrame] = []

    branches = basket_df["branch"].unique() if "branch" in basket_df.columns else ["ALL"]

    for branch in branches:
        subset = basket_df[basket_df["branch"] == branch] if branch != "ALL" else basket_df
        rules = compute_association_rules(subset, min_support, min_confidence, top_k)
        if not rules.empty:
            rules = rules.copy()
            rules.insert(0, "branch", branch)
            all_rules.append(rules)
            _log.info("  Branch %-30s → %d rules", branch, len(rules))
        else:
            _log.warning("  Branch %-30s → no rules found", branch)

    # Global rules
    global_rules = compute_association_rules(basket_df, min_support, min_confidence, top_k)
    if not global_rules.empty:
        global_rules = global_rules.copy()
        global_rules.insert(0, "branch", "ALL")
        all_rules.append(global_rules)

    if not all_rules:
        _log.warning("No association rules generated for any branch.")
        return pd.DataFrame(
            columns=["branch", "antecedents", "consequents", "support", "confidence", "lift"]
        )

    combined = pd.concat(all_rules, ignore_index=True)
    return combined
