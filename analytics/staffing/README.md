# Business Model 4: Shift Staffing Estimation

This package implements a standalone staffing estimator for Conut's Business Model 4.

It does not modify the main pipeline. It reads already-cleaned inputs from `pipelines/output/` and writes its own outputs into `pipelines/business_model_4_staffing_estimation/output/`.

## Purpose

The estimator compares:

- employee availability over time, reconstructed from `attendance.csv`
- estimated demand over time, inferred from `customer_orders.csv`
- channel-level scaling factors from `avg_sales_menu.csv`

The result is an hourly staffing-gap view by branch, day of week, and hour.

All generated branch/day/hour tables are restricted to staffed operating slots only. Hours with zero active employees are excluded so they do not distort averages or recommendations.

## Package Structure

```text
pipelines/business_model_4_staffing_estimation/
├── __init__.py
├── analyze.py
├── config.py
├── loaders.py
├── supply.py
├── demand.py
├── model.py
├── visualize.py
└── README.md
```

## Files And Responsibilities

### `analyze.py`

Main entrypoint.

What it does:
- loads the cleaned pipeline outputs
- infers the valid overlap window from attendance data
- builds hourly staffing supply
- builds hourly delivery-demand shape
- derives demand multipliers
- estimates total hourly demand
- calibrates a target productivity ratio
- estimates required employees and staffing gaps
- saves all output tables

Inputs:
- `pipelines/output/attendance.csv`
- `pipelines/output/customer_orders.csv`
- `pipelines/output/avg_sales_menu.csv`
- `pipelines/output/dim_branch.csv`

Outputs:
- all CSVs listed in the Output Tables section below

Run:

```bash
python pipelines/business_model_4_staffing_estimation/analyze.py
```

### `config.py`

Central constants and paths.

What it contains:
- package and project paths
- weekday ordering
- delivery-share bounds
- scenario spreads for low/base/high demand
- minimum productivity floor

### `loaders.py`

Input loading and normalization layer.

What it does:
- reads the required cleaned CSVs
- normalizes dates, numbers, and booleans
- infers the common analysis window from valid attendance shifts

Main functions:
- `load_input_tables()`
- `infer_overlap_window()`

### `supply.py`

Builds the staffing-side time series.

What it does:
- keeps only valid shifts
- converts `date + punch_in/punch_out` into real timestamps
- handles overnight shifts by rolling `punch_out` into the next day when needed
- expands each shift into overlapping hourly buckets
- counts unique active employees per branch/date/hour
- aggregates that daily series into a branch/day/hour supply profile

Main functions:
- `build_attendance_hourly_supply()`
- `build_supply_profile()`

### `demand.py`

Builds the demand-side time series and the delivery-to-total scaling logic.

What it does:
- filters customer records to the attendance overlap window
- uses `last_order` only as a temporal-shape proxy
- uses `num_orders` only to preserve total branch delivery volume
- creates a branch/day/hour demand shape
- smooths very sparse branch demand shapes across staffed slots so a few proxy rows do not dominate the whole recommendation
- derives delivery-share multipliers from `avg_sales_menu.csv`
- adds a revenue-based uplift when a low-confidence branch has much higher recent sales than its proxy demand suggests
- falls back to inferred shares from customer profiles when the delivery row is missing
- builds low/base/high total-demand scenarios

Main functions:
- `build_delivery_demand_shape()`
- `build_branch_demand_multipliers()`
- `estimate_total_hourly_demand()`

### `model.py`

Calibration and recommendation layer.

What it does:
- learns a robust target `orders per employee` productivity ratio from historical branch behavior
- uses medians with outlier trimming instead of raw means
- prevents sparse low-confidence branches from self-calibrating to unrealistically high productivity targets
- estimates required staff under low/base/high demand scenarios
- computes staffing gaps
- summarizes branch-level findings

Main functions:
- `shift_bucket_from_hour()`
- `build_target_productivity_reference()`
- `estimate_required_staff()`
- `summarize_staffing_findings()`

### `visualize.py`

Visualization and reporting entrypoint.

What it does:
- reads the generated staffing analysis outputs
- creates summary CSV tables for easier review

Main outputs:
- `branch_summary_view.csv`
- `top_gap_slots.csv`

Run:

```bash
python pipelines/business_model_4_staffing_estimation/visualize.py
```

## Output Tables

### `staffing_supply_hourly.csv`

Daily hourly staffing time series built from attendance.

Columns:
- `branch`: branch name
- `date`: actual calendar date of the hour slot
- `day_of_week`: weekday name derived from the hourly slot
- `hour`: hour bucket from `0` to `23`
- `active_employees`: unique employees active during that hour
- `active_shift_rows`: number of valid shift rows contributing to that slot

### `delivery_demand_shape_hourly.csv`

Hourly delivery-shape proxy aligned to the attendance window and restricted to staffed slots only.

Columns:
- `branch`: branch name
- `day_of_week`: weekday name
- `hour`: hour bucket from `0` to `23`
- `support_rows`: number of customer records whose `last_order` falls in the slot
- `slot_num_orders`: sum of `num_orders` attached to those customer records
- `branch_total_customer_rows_in_overlap`: branch customer-record count in the overlap window
- `branch_total_num_orders_in_overlap`: branch total `num_orders` in the overlap window
- `branch_staffed_slot_count`: number of staffed branch/day/hour slots available for distribution
- `shape_weight_rows`: slot weight based on record count
- `shape_weight_num_orders`: slot weight based on `num_orders`
- `shape_support_strength`: how much the slot shape trusts observed proxy rows versus smoothed distribution

### `branch_demand_multipliers.csv`

Branch-level scaling from delivery demand to estimated total demand.

Columns:
- `branch`: branch name
- `avg_sales_total_customers`: total customers from `avg_sales_menu.csv`
- `avg_sales_delivery_customers`: delivery customers from `avg_sales_menu.csv`
- `avg_sales_delivery_share`: delivery customer share from `avg_sales_menu.csv`
- `delivery_customer_profiles`: number of customer profiles in `customer_orders.csv`
- `delivery_num_orders`: summed `num_orders` from `customer_orders.csv`
- `observed_profile_share`: inferred delivery share from profile counts versus total customers
- `share_source`: which rule produced the final share
- `confidence`: `high`, `medium`, or `low`
- `note`: reason for fallback or mismatch
- `recent_revenue_month`: latest month available from `monthly_sales.csv`
- `recent_revenue`: latest monthly revenue for the branch
- `recent_revenue_share_staffed_branches`: branch revenue share among staffed branches
- `overlap_proxy_order_share`: branch share of proxy orders inside the staffing overlap window
- `sales_to_proxy_gap_ratio`: how much sales share exceeds proxy-demand share
- `sales_calibration_multiplier`: extra uplift applied to low-confidence demand multipliers
- `delivery_share_low`: high-delivery-share case used for low total-demand scenario
- `delivery_share_base`: base delivery share
- `delivery_share_high`: low-delivery-share case used for high total-demand scenario
- `multiplier_low_demand`: multiplier for the low total-demand scenario
- `multiplier_base_demand`: multiplier for the base scenario
- `multiplier_high_demand`: multiplier for the high-demand scenario

### `target_productivity_reference.csv`

Reference productivity levels used to translate demand into required employees.

Columns:
- `branch`: branch name or `__global__`
- `shift_bucket`: `morning`, `afternoon`, `evening`, `overnight`, or `all_day`
- `slot_count`: number of staffed slots used in the calibration
- `median_observed_orders_per_employee`: raw median before fallback logic
- `target_orders_per_employee`: final robust target used for recommendations
- `reference_level`: `branch_shift`, `branch_all_day`, or `global`

### `total_demand_est_hourly.csv`

Hourly demand estimate with uncertainty scenarios, limited to staffed branch/day/hour slots.

Columns:
- all columns from `delivery_demand_shape_hourly.csv`
- branch-level multiplier metadata from `branch_demand_multipliers.csv`
- `delivery_orders_est`: delivery orders allocated to the slot
- `total_orders_est_low`: low total-demand estimate
- `total_orders_est_base`: base total-demand estimate
- `total_orders_est_high`: high total-demand estimate

### `staffing_gap_hourly.csv`

Final branch/day/hour staffing recommendation table.

Important behavior:
- this table contains only slots where the branch has observed staffing coverage
- zero-employee filler hours are excluded
- summary averages therefore reflect relevant staffed operating hours only
- recommended employees are floored at `1` for every staffed slot, even when estimated demand is near zero

Columns:
- `branch`, `day_of_week`, `hour`
- supply-profile fields such as `avg_active_employees`, `median_active_employees`, `observed_days`
- demand fields such as `delivery_orders_est`, `total_orders_est_base`
- `shift_bucket`: operational shift label
- `shift_target`: branch-and-shift productivity target when available
- `branch_target`: branch-wide fallback target
- `target_orders_per_employee`: final target after fallback
- `required_employees_low`, `required_employees_base`, `required_employees_high`
- `gap_low`, `gap_base`, `gap_high`
- `status`: `understaffed`, `balanced`, or `overstaffed`

### `branch_staffing_findings.csv`

Business-facing branch summary.

Columns:
- `branch`
- `demand_confidence`
- `share_source`
- `analysis_slots`
- `understaffed_slots`
- `balanced_slots`
- `overstaffed_slots`
- `avg_active_employees_across_slots`
- `avg_required_employees_base`
- `worst_understaffed_slot`
- `worst_understaffed_gap`
- `worst_overstaffed_slot`
- `worst_overstaffed_gap`
- `top_understaffed_slots`
- `top_overstaffed_slots`
- `recommendation`

## Summary Outputs

After running `visualize.py`, the package also creates:

- `branch_summary_view.csv`: compact branch-level operating summary for presentation
- `top_gap_slots.csv`: highest-impact understaffed or overstaffed slots by branch

## Modeling Notes

- This is a transparent decision-support model, not a supervised ML model.
- `attendance.csv` is the staffing source of truth.
- `customer_orders.csv` is treated as a delivery-demand proxy, not a full order-event log.
- `avg_sales_menu.csv` is used to scale delivery demand into total demand using customer-share logic.
- When `avg_sales_menu.csv` has no delivery row for a branch, the package falls back to a low-confidence inferred share.
- Recommendations should therefore be interpreted together with the `confidence` field.

## Limitations

- Branches without attendance data are intentionally excluded from direct staffing recommendations.
- Demand timing is inferred from customer-level timestamps, not individual order events.
- If delivery and channel tables disagree strongly, the branch remains analyzable but is marked lower-confidence.
