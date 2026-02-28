#!/usr/bin/env python3
"""
Orchestrator — scans the raw-data directory, auto-detects each CSV's report
type via utils.detect_report_type(), routes it to the matching parser, and
saves cleaned DataFrames to pipelines/output/.

After parsing, builds:
  - Dimension tables (dim_branch, dim_item)
  - Reconciliation checks (fact_reconciliation_checks)
  - Feature store (feat_branch_month, feat_branch_item, feat_customer_delivery, feat_branch_shift)

Usage:
    python pipelines/run_pipeline.py
    python pipelines/run_pipeline.py --data-dir path/to/csvs
"""

import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

# Ensure the project root (parent of `pipelines/`) is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.parsers import (
    monthly_sales,
    items_by_group,
    avg_sales_menu,
    customer_orders,
    transaction_baskets,
    attendance,
)
from pipelines.parsers.utils import detect_report_type, read_lines
from pipelines.parsers.dimensions import build_dim_branch, build_dim_item
from pipelines.parsers.reconciliation import build_reconciliation
from pipelines.parsers.features import (
    build_feat_branch_month,
    build_feat_branch_item,
    build_feat_customer_delivery,
    build_feat_branch_shift,
)

# ── parser registry ──────────────────────────────────────────────────────────
# Maps report-type keys (returned by detect_report_type) to parser modules
REGISTRY = {
    "monthly_sales":       monthly_sales,
    "items_by_group":      items_by_group,
    "avg_sales_menu":      avg_sales_menu,
    "customer_orders":     customer_orders,
    "transaction_baskets": transaction_baskets,
    "attendance":          attendance,
}

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def _save(df: pd.DataFrame, name: str, dest: dict, verbose: bool) -> None:
    """Save a DataFrame to OUTPUT_DIR and register in dest dict."""
    path = OUTPUT_DIR / name
    df.to_csv(path, index=False)
    dest[name] = df
    if verbose:
        print(f"         ↳ {name}  ({len(df)} rows × {len(df.columns)} cols)")


def file_hash(filepath: str) -> str:
    """Quick content hash (first 8KB) for duplicate detection."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        h.update(f.read(8192))
    return h.hexdigest()


def discover_csvs(data_dir: str) -> list[Path]:
    """Return all .csv files in data_dir, sorted by name."""
    d = Path(data_dir)
    if not d.is_dir():
        print(f"ERROR: data directory not found: {d}")
        sys.exit(1)
    return sorted(d.glob("*.csv"))


def run(data_dir: str, verbose: bool = True) -> dict:
    """
    Main pipeline entry.
    Returns dict of {output_filename: DataFrame} for downstream use.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csvs = discover_csvs(data_dir)

    if not csvs:
        print(f"No CSV files found in {data_dir}")
        return {}

    seen_hashes: dict[str, str] = {}
    results: dict[str, pd.DataFrame] = {}
    skipped: list[str] = []
    errors: list[str] = []

    for csv_path in csvs:
        name = csv_path.name
        h = file_hash(str(csv_path))

        # ── duplicate detection ──
        if h in seen_hashes:
            skipped.append(f"{name} (duplicate of {seen_hashes[h]})")
            if verbose:
                print(f"  SKIP  {name}  (duplicate of {seen_hashes[h]})")
            continue
        seen_hashes[h] = name

        # ── detect report type ──
        try:
            lines = read_lines(str(csv_path))
        except Exception as exc:
            errors.append(f"{name}: read error — {exc}")
            continue

        rtype = detect_report_type(lines)
        if rtype is None:
            skipped.append(f"{name} (unknown report type)")
            if verbose:
                print(f"  SKIP  {name}  (unknown report type)")
            continue

        parser = REGISTRY.get(rtype)
        if parser is None:
            skipped.append(f"{name} (no parser for {rtype})")
            if verbose:
                print(f"  SKIP  {name}  (no parser registered for '{rtype}')")
            continue

        # ── double-check with parser's own can_parse ──
        if not parser.can_parse(lines):
            skipped.append(f"{name} (can_parse=False for {rtype})")
            if verbose:
                print(f"  SKIP  {name}  (parser.can_parse returned False)")
            continue

        # ── parse ──
        if verbose:
            print(f"  PARSE {name}  →  {rtype}")
        try:
            result = parser.parse(str(csv_path))
        except Exception as exc:
            errors.append(f"{name}: parse error — {exc}")
            if verbose:
                print(f"  ERROR {name}: {exc}")
            continue

        # ── save ──
        if isinstance(result, tuple):
            # transaction_baskets returns (raw_lines, audit_lines, basket_core)
            suffixes = ("raw_lines", "audit_lines", "basket_core")
            for df, suffix in zip(result, suffixes):
                out_name = f"{rtype}_{suffix}.csv"
                out_path = OUTPUT_DIR / out_name
                df.to_csv(out_path, index=False)
                results[out_name] = df
                if verbose:
                    print(f"         ↳ {out_name}  ({len(df)} rows × {len(df.columns)} cols)")
        else:
            out_name = f"{rtype}.csv"
            out_path = OUTPUT_DIR / out_name
            result.to_csv(out_path, index=False)
            results[out_name] = result
            if verbose:
                print(f"         ↳ {out_name}  ({len(result)} rows × {len(result.columns)} cols)")

    # ── Post-parse layers ────────────────────────────────────────────────────
    if verbose:
        print("\n── Building dimensions, reconciliation, features ──")

    ms = results.get("monthly_sales.csv", pd.DataFrame())
    ig = results.get("items_by_group.csv", pd.DataFrame())
    asm = results.get("avg_sales_menu.csv", pd.DataFrame())
    co = results.get("customer_orders.csv", pd.DataFrame())
    att = results.get("attendance.csv", pd.DataFrame())

    layers: dict[str, pd.DataFrame] = {}

    # Dimension tables
    try:
        dim_b = build_dim_branch(asm, ms, att)
        _save(dim_b, "dim_branch.csv", layers, verbose)
    except Exception as exc:
        errors.append(f"dim_branch: {exc}")

    try:
        dim_i = build_dim_item(ig)
        _save(dim_i, "dim_item.csv", layers, verbose)
    except Exception as exc:
        errors.append(f"dim_item: {exc}")

    # Reconciliation
    try:
        recon = build_reconciliation(ms, asm, ig)
        _save(recon, "fact_reconciliation_checks.csv", layers, verbose)
    except Exception as exc:
        errors.append(f"reconciliation: {exc}")

    # Feature store
    try:
        fbm = build_feat_branch_month(ms, asm, ig)
        _save(fbm, "feat_branch_month.csv", layers, verbose)
    except Exception as exc:
        errors.append(f"feat_branch_month: {exc}")

    try:
        fbi = build_feat_branch_item(ig)
        _save(fbi, "feat_branch_item.csv", layers, verbose)
    except Exception as exc:
        errors.append(f"feat_branch_item: {exc}")

    try:
        fcd = build_feat_customer_delivery(co)
        _save(fcd, "feat_customer_delivery.csv", layers, verbose)
    except Exception as exc:
        errors.append(f"feat_customer_delivery: {exc}")

    try:
        fbs = build_feat_branch_shift(att)
        _save(fbs, "feat_branch_shift.csv", layers, verbose)
    except Exception as exc:
        errors.append(f"feat_branch_shift: {exc}")

    results.update(layers)

    # ── summary ──
    if verbose:
        print("\n" + "=" * 60)
        print(f"  Parsed:  {len(results)} output files")
        print(f"  Skipped: {len(skipped)}")
        if skipped:
            for s in skipped:
                print(f"           • {s}")
        if errors:
            print(f"  Errors:  {len(errors)}")
            for e in errors:
                print(f"           • {e}")
        print("=" * 60)

    return results


# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    default_data = str(PROJECT_ROOT / "Conut bakery Scaled Data ")
    parser = argparse.ArgumentParser(description="Conut data-processing pipeline")
    parser.add_argument("--data-dir", default=default_data, help="Path to raw CSV directory")
    args = parser.parse_args()

    print(f"Data dir: {args.data_dir}\n")
    run(args.data_dir)
