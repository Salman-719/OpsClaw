"""
Reconciliation layer — cross-source validation checks.

Produces a fact_reconciliation_checks table that formalises which files
agree / disagree and by how much, establishing a source-of-truth hierarchy.

Source-of-truth hierarchy:
  branch revenue     → monthly_sales
  channel mix        → avg_sales_menu
  product mix        → items_by_group
  staffing           → attendance (cleaned)
  delivery customers → customer_orders
"""

import pandas as pd


TOLERANCE_PCT = 0.10  # 10 % default tolerance


def build_reconciliation(
    monthly_sales_df: pd.DataFrame,
    avg_sales_df: pd.DataFrame,
    items_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compare overlapping metrics across source files.
    Returns a long-form reconciliation table.
    """
    checks: list[dict] = []

    # ── Check 1: branch total revenue — monthly_sales vs avg_sales_menu ──
    if (
        monthly_sales_df is not None and not monthly_sales_df.empty
        and avg_sales_df is not None and not avg_sales_df.empty
    ):
        ms_total = monthly_sales_df.groupby("branch")["revenue"].sum()
        as_total = avg_sales_df.groupby("branch")["sales"].sum()

        for branch in set(ms_total.index) & set(as_total.index):
            val_a = ms_total[branch]
            val_b = as_total[branch]
            var = abs(val_a - val_b) / max(val_a, 1)
            checks.append({
                "branch": branch,
                "source_a": "monthly_sales",
                "source_b": "avg_sales_menu",
                "metric": "total_revenue",
                "value_a": round(val_a, 2),
                "value_b": round(val_b, 2),
                "variance_pct": round(var, 4),
                "is_within_tolerance": var <= TOLERANCE_PCT,
                "note": "monthly_sales is revenue truth; avg_sales is channel aggregate",
            })

    # ── Check 2: branch total revenue — monthly_sales vs items_by_group ──
    if (
        monthly_sales_df is not None and not monthly_sales_df.empty
        and items_df is not None and not items_df.empty
    ):
        ms_total = monthly_sales_df.groupby("branch")["revenue"].sum()
        # items revenue = sum of non-modifier amounts
        ig_paid = items_df[~items_df["is_modifier"]] if "is_modifier" in items_df.columns else items_df
        ig_total = ig_paid.groupby("branch")["amount"].sum()

        for branch in set(ms_total.index) & set(ig_total.index):
            val_a = ms_total[branch]
            val_b = ig_total[branch]
            var = abs(val_a - val_b) / max(val_a, 1)
            checks.append({
                "branch": branch,
                "source_a": "monthly_sales",
                "source_b": "items_by_group",
                "metric": "total_revenue",
                "value_a": round(val_a, 2),
                "value_b": round(val_b, 2),
                "variance_pct": round(var, 4),
                "is_within_tolerance": var <= TOLERANCE_PCT,
                "note": "items_by_group is mix truth, not revenue truth",
            })

    # ── Check 3: avg_sales total vs items_by_group per branch ──
    if (
        avg_sales_df is not None and not avg_sales_df.empty
        and items_df is not None and not items_df.empty
    ):
        as_total = avg_sales_df.groupby("branch")["sales"].sum()
        ig_paid = items_df[~items_df["is_modifier"]] if "is_modifier" in items_df.columns else items_df
        ig_total = ig_paid.groupby("branch")["amount"].sum()

        for branch in set(as_total.index) & set(ig_total.index):
            val_a = as_total[branch]
            val_b = ig_total[branch]
            var = abs(val_a - val_b) / max(val_a, 1)
            checks.append({
                "branch": branch,
                "source_a": "avg_sales_menu",
                "source_b": "items_by_group",
                "metric": "total_revenue",
                "value_a": round(val_a, 2),
                "value_b": round(val_b, 2),
                "variance_pct": round(var, 4),
                "is_within_tolerance": var <= TOLERANCE_PCT,
                "note": "cross-check channel aggregate vs product aggregate",
            })

    df = pd.DataFrame(checks)
    if not df.empty:
        df = df.sort_values(["branch", "metric", "source_a"]).reset_index(drop=True)
    return df
