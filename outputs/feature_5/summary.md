# Feature 5: Coffee & Milkshake Growth Strategy
## Beverage Attachment Summary

- **Best branch**: Main Street Coffee — 28.6% attachment rate
- **Most-lagging branch**: Conut Jnah — 15.3% (gap to best: 13.3%)

## Growth Potential Ranking

- **Conut Jnah**: score=1.000 (rank 1) — hot chocolate combo → oreo milkshake (lift=98.00)
- **Conut - Tyre**: score=0.168 (rank 2) — conut the one → mocha frappe (lift=9.00)
- **Main Street Coffee**: score=0.049 (rank 3) — hot chocolate → double chocolate milkshake (lift=14.00)

## How to Interpret

- `beverage_attachment_rate`: proportion of orders containing at least one coffee/milkshake.
- `beverage_gap_to_best`: percentage points below the top-performing branch.
- `potential_score` (0-1): composite score weighting low attachment (35%),
  large order volume (35%), and strong food→beverage association lift (30%).
- `top_bundle_rule`: the single highest-lift food item that predicts a beverage purchase.

## Recommended Actions

1. Focus promotions on high-potential branches (score ≥ 0.5).
2. Use the top bundle rule per branch to design combo offers
   (e.g., 'Add a coffee for X% off when ordering [antecedent item]').
3. Set branch KPI target: close 50% of the gap to best within one quarter.