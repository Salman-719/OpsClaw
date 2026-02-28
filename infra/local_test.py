#!/usr/bin/env python3
"""
Local test runner — exercises all handlers without AWS credentials.

Usage:
    python infra/local_test.py            # run all
    python infra/local_test.py etl        # ETL only
    python infra/local_test.py forecast   # forecast only
    python infra/local_test.py combo      # combo only
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_etl():
    print("=" * 60)
    print("  LOCAL TEST — ETL Handler")
    print("=" * 60)
    from infra.handlers.etl_handler import run_local
    result = run_local()
    print(json.dumps(result, indent=2, default=str))
    assert result["status"] == "success", f"ETL failed: {result}"
    print(f"\n✓ ETL produced {len(result['output_files'])} files.\n")
    return result


def test_forecast():
    print("=" * 60)
    print("  LOCAL TEST — Forecast Handler")
    print("=" * 60)
    from infra.handlers.forecast_handler import run_local
    result = run_local()
    print(json.dumps(result, indent=2, default=str))
    assert result["status"] == "success", f"Forecast failed: {result}"
    assert result["total_rows"] == 24, f"Expected 24 rows, got {result['total_rows']}"
    print(f"\n✓ Forecast produced {result['total_rows']} rows.\n")
    return result


def test_combo():
    print("=" * 60)
    print("  LOCAL TEST — Combo Handler")
    print("=" * 60)
    from infra.handlers.combo_handler import run_local
    result = run_local()
    print(json.dumps(result, indent=2, default=str))
    assert result["status"] == "success", f"Combo failed: {result}"
    assert result["total_pairs"] > 0, f"Expected >0 pairs, got {result['total_pairs']}"
    print(f"\n✓ Combo produced {result['total_baskets']} baskets, {result['total_pairs']} pairs.\n")
    return result


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    if target in ("all", "etl"):
        test_etl()

    if target in ("all", "forecast"):
        test_forecast()

    if target in ("all", "combo"):
        test_combo()

    print("All local tests passed.")
