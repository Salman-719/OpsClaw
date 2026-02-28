"""
Unit tests — ETL pipeline parsers and orchestrator.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure project root importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.parsers.utils import detect_report_type, read_lines

# ---------------------------------------------------------------------------
# detect_report_type
# ---------------------------------------------------------------------------

class TestDetectReportType:
    def test_known_type_returns_key(self):
        lines = ["Monthly Sales Summary", "Branch,Jan,Feb", "A,1,2"]
        result = detect_report_type(lines)
        assert result == "monthly_sales"

    def test_unknown_returns_none(self):
        lines = ["random stuff", "col_a,col_b", "1,2"]
        result = detect_report_type(lines)
        assert result is None

    def test_attendance_detected(self):
        lines = ["Time & Attendance Report", "Employee,Hours", "Alice,8"]
        result = detect_report_type(lines)
        assert result == "attendance"

    def test_items_by_group_detected(self):
        lines = ["Sales by Items by Group", "Group,Amount"]
        result = detect_report_type(lines)
        assert result == "items_by_group"


# ---------------------------------------------------------------------------
# Pipeline orchestrator (run_pipeline)
# ---------------------------------------------------------------------------

class TestRunPipeline:
    def test_output_dir_exists(self):
        from pipelines.run_pipeline import OUTPUT_DIR
        assert isinstance(OUTPUT_DIR, Path)

    def test_registry_has_all_parsers(self):
        from pipelines.run_pipeline import REGISTRY
        expected = {"monthly_sales", "items_by_group", "avg_sales_menu",
                    "customer_orders", "transaction_baskets", "attendance"}
        assert expected == set(REGISTRY.keys())

    def test_run_with_real_data(self):
        """Integration: run the full ETL on the shipped sample data."""
        from pipelines.run_pipeline import run, OUTPUT_DIR
        data_dir = PROJECT_ROOT / "conut_bakery_scaled_data"
        if not data_dir.exists():
            pytest.skip("Sample data not found")

        results = run(str(data_dir), verbose=False)
        assert isinstance(results, dict)
        assert len(results) > 0
        # Output CSVs should exist — the keys already include .csv extension
        for name in results:
            out_file = OUTPUT_DIR / name if name.endswith(".csv") else OUTPUT_DIR / f"{name}.csv"
            assert out_file.exists(), f"Missing output: {out_file}"
