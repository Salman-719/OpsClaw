"""
Dimension builders — derive dim_branch and dim_item from pipeline outputs.

These are small reference tables that make downstream joins cleaner:
  dim_branch:  canonical names, branch type, channel flags
  dim_item:    canonical item name, division, group, category hierarchy, flags
"""

import pandas as pd


def build_dim_branch(
    avg_sales_df: pd.DataFrame,
    monthly_sales_df: pd.DataFrame,
    attendance_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build a branch dimension table from parsed pipeline outputs.

    Columns:
        canonical_branch_name, has_delivery, has_table, has_takeaway,
        has_attendance_data, has_monthly_sales, months_of_data
    """
    branches = set()
    for df in (avg_sales_df, monthly_sales_df, attendance_df):
        if df is not None and not df.empty and "branch" in df.columns:
            branches.update(df["branch"].unique())

    rows = []
    for b in sorted(branches):
        row = {"canonical_branch_name": b}

        # Channel flags from avg_sales
        if avg_sales_df is not None and not avg_sales_df.empty:
            bdata = avg_sales_df[avg_sales_df["branch"] == b]
            channels = set(bdata["channel"].str.upper()) if not bdata.empty else set()
            row["has_delivery"] = "DELIVERY" in channels
            row["has_table"] = "TABLE" in channels
            row["has_takeaway"] = "TAKE AWAY" in channels
        else:
            row["has_delivery"] = None
            row["has_table"] = None
            row["has_takeaway"] = None

        # Monthly sales coverage
        if monthly_sales_df is not None and not monthly_sales_df.empty:
            bms = monthly_sales_df[monthly_sales_df["branch"] == b]
            row["has_monthly_sales"] = not bms.empty
            row["months_of_data"] = len(bms)
        else:
            row["has_monthly_sales"] = None
            row["months_of_data"] = 0

        # Attendance coverage
        if attendance_df is not None and not attendance_df.empty:
            row["has_attendance_data"] = b in attendance_df["branch"].values
        else:
            row["has_attendance_data"] = None

        rows.append(row)

    return pd.DataFrame(rows)


def build_dim_item(items_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build an item dimension table from the items_by_group output.

    Columns:
        canonical_item_name, division, group, category,
        beverage_flag, modifier_flag
    """
    if items_df is None or items_df.empty:
        return pd.DataFrame(columns=[
            "canonical_item_name", "division", "group", "category",
            "beverage_flag", "modifier_flag",
        ])

    # One row per unique item (take the first occurrence's hierarchy)
    dim = (
        items_df.groupby("item")
        .agg(
            division=("division", "first"),
            group=("group", "first"),
            category=("category", "first"),
            modifier_flag=("is_modifier", "any"),
        )
        .reset_index()
        .rename(columns={"item": "canonical_item_name"})
    )

    dim["beverage_flag"] = dim["category"].isin([
        "coffee_hot", "coffee_cold", "milkshake", "other_beverage",
    ])

    return dim.sort_values("canonical_item_name").reset_index(drop=True)
