"""
loader.py – Load and validate input DataFrames for Feature 5.

Expected files (relative to *data_dir*):
  - feat_branch_item.csv
  - transaction_baskets_basket_core.csv
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd

from .utils import get_logger

_log = get_logger(__name__)

# Canonical column names used downstream
BRANCH_ITEM_COLS = {
    "branch": str,
    "item": str,
    "category": str,
    "qty": float,
    "amount": float,
}

BASKET_COLS = {
    "basket_id": object,
    "branch": str,
    "items_list": str,
}


def load_branch_item(data_dir: str | Path) -> pd.DataFrame:
    """
    Load *feat_branch_item.csv* and coerce column types.

    Returns a DataFrame with at minimum: branch, item, category, qty, amount.
    Additional columns (item_share, item_rank, attach_tendency,
    beverage_opportunity_flag) are retained if present.
    """
    path = Path(data_dir) / "feat_branch_item.csv"
    _log.info("Loading feat_branch_item from %s", path)
    df = pd.read_csv(path)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Coerce numeric columns
    for col, dtype in BRANCH_ITEM_COLS.items():
        if col in df.columns and dtype in (float, int):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Fill empty strings
    for col in ("branch", "item", "category"):
        if col in df.columns:
            df[col] = df[col].fillna("").str.strip()

    _log.info("feat_branch_item: %d rows, branches=%s", len(df), df["branch"].unique().tolist())
    return df


def load_basket_core(data_dir: str | Path) -> pd.DataFrame:
    """
    Load *transaction_baskets_basket_core.csv*.

    Returns a DataFrame with at minimum: basket_id, branch, items_list.
    """
    path = Path(data_dir) / "transaction_baskets_basket_core.csv"
    _log.info("Loading transaction_baskets_basket_core from %s", path)
    df = pd.read_csv(path)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Coerce numerics if present
    for col in ("net_qty", "net_total", "unique_items"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ("branch", "customer"):
        if col in df.columns:
            df[col] = df[col].fillna("").str.strip()

    df["items_list"] = df["items_list"].fillna("[]")

    _log.info(
        "basket_core: %d rows, branches=%s",
        len(df),
        df["branch"].unique().tolist() if "branch" in df.columns else "N/A",
    )
    return df


def load_all(data_dir: str | Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Convenience loader: returns (branch_item_df, basket_core_df).

    Parameters
    ----------
    data_dir : str | Path
        Directory that contains both CSV files.
    """
    return load_branch_item(data_dir), load_basket_core(data_dir)
