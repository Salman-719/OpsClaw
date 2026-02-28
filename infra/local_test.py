#!/usr/bin/env python3
"""
Local test runner — exercises all handlers without AWS credentials.

Usage:
    python infra/local_test.py              # run all
    python infra/local_test.py etl          # ETL only
    python infra/local_test.py forecast     # forecast only
    python infra/local_test.py combo        # combo only
    python infra/local_test.py expansion    # expansion only
    python infra/local_test.py staffing     # staffing only
    python infra/local_test.py growth       # growth only
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


def test_expansion():
    print("=" * 60)
    print("  LOCAL TEST — Expansion Handler")
    print("=" * 60)
    from infra.handlers.expansion_handler import run_local
    result = run_local()
    print(json.dumps(result, indent=2, default=str))
    assert result["status"] == "success", f"Expansion failed: {result}"
    assert result["total_kpi_rows"] > 0, f"Expected >0 KPI rows, got {result['total_kpi_rows']}"
    print(f"\n✓ Expansion: {result['total_kpi_rows']} KPIs, {result['total_score_rows']} scores, "
          f"region={result['recommendation_region']}.\n")
    return result


def test_staffing():
    print("=" * 60)
    print("  LOCAL TEST — Staffing Handler")
    print("=" * 60)
    from infra.handlers.staffing_handler import run_local
    result = run_local()
    print(json.dumps(result, indent=2, default=str))
    assert result["status"] == "success", f"Staffing failed: {result}"
    assert result["findings_rows"] > 0, f"Expected >0 findings rows, got {result['findings_rows']}"
    print(f"\n✓ Staffing: {result['findings_rows']} branch findings, "
          f"{result['gap_rows']} gap rows, {len(result['output_files'])} output files.\n")
    return result


def test_growth():
    print("=" * 60)
    print("  LOCAL TEST — Growth Handler")
    print("=" * 60)
    from infra.handlers.growth_handler import run_local
    result = run_local()
    print(json.dumps(result, indent=2, default=str))
    assert result["status"] == "success", f"Growth failed: {result}"
    assert result["growth_rows"] > 0, f"Expected >0 growth rows, got {result['growth_rows']}"
    print(f"\n✓ Growth: {result['kpi_rows']} KPIs, {result['growth_rows']} growth rows, "
          f"{result['rules_rows']} rules, strategy={result['recommendation_strategy']}.\n")
    return result


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    if target in ("all", "etl"):
        test_etl()

    if target in ("all", "forecast"):
        test_forecast()

    if target in ("all", "combo"):
        test_combo()

    if target in ("all", "expansion"):
        test_expansion()

    if target in ("all", "staffing"):
        test_staffing()

    if target in ("all", "growth"):
        test_growth()

    print("All local tests passed.")
