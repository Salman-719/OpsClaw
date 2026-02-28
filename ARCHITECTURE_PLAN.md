# Conut Chief of Operations Agent — Architecture Plan

## 0. High-Level View

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              GitHub Repository                                     │
├────────────┬─────────────┬──────────────┬──────────┬──────────────┬────────────────┤
│  Layer 0   │  Layer 1    │  Layer 2     │ Layer 2½ │  Layer 3     │   Layer 4      │
│  Data ETL  │  Analytics  │  Agent Core  │ Service  │  OpenClaw    │  Delivery      │
│  (DONE)    │  & Engines  │  (LLM glue)  │ (API)    │  (adapter)   │  & Demo        │
├────────────┼─────────────┼──────────────┼──────────┼──────────────┼────────────────┤
│ pipelines/ │ analytics/  │ agent/       │ service/ │ openclaw/    │ docs/          │
│  parsers/  │  combo.py   │  tools.py    │ router.py│  config.yaml │ README.md      │
│  output/   │  forecast/  │  formatter.py│ contra.py│  handlers.py │ exec_brief.pdf │
│  features  │  expand.py  │  prompts.py  │ cache.py │              │ demo/          │
│  dims      │  staff.py   │  engine.py   │          │              │                │
│  recon     │  growth.py  │  router.py   │          │              │                │
│            │             │              │          │              │                │
│            │ artifacts/  │              │          │              │                │
│            │  (cached)   │              │          │              │                │
└────────────┴─────────────┴──────────────┴──────────┴──────────────┴────────────────┘
```

**Data flows left-to-right:** raw CSVs → clean tables → analytical results → artifacts cache → agent-callable tools → service API → OpenClaw adapter → user-facing answers.

**Key architectural additions over v1:**
- **`service/`** — thin API layer between Agent and OpenClaw; keeps OpenClaw as a pure adapter, enables CLI/local-API fallback if OpenClaw hiccups.
- **`agent/formatter.py`** — all natural-language rendering lives here, not inside analytics modules (separation of concerns).
- **`agent/router.py`** — rule-based intent classifier as fallback when LLM API is unavailable.
- **`artifacts/`** — materialized analytics outputs for demo stability, reproducibility, and faster inference.

---

## 1. Layer 0 — Data ETL (DONE)

Already built in `pipelines/`. Produces 15 CSVs across 4 tiers:

| Tier | Files | Purpose |
|---|---|---|
| Parser outputs (8) | `monthly_sales`, `items_by_group`, `avg_sales_menu`, `customer_orders`, `transaction_baskets_*` (3), `attendance` | Cleaned source tables |
| Dimensions (2) | `dim_branch`, `dim_item` | Lookup / enrichment |
| Reconciliation (1) | `fact_reconciliation_checks` | Cross-source trust validation |
| Feature store (4) | `feat_branch_month`, `feat_branch_item`, `feat_customer_delivery`, `feat_branch_shift` | Model-ready features |

**No changes needed.** Layer 1 reads from `pipelines/output/`.

---

## 2. Layer 1 — Analytics & Decision Engines (`analytics/`)

One module per business objective. Each module exposes a deterministic `run()` function that returns **structured results only** (dict/DataFrame). Natural-language summaries are handled separately by `agent/formatter.py` — this keeps business logic and presentation logic cleanly separated, making each layer independently testable.

### 2A. Combo Optimization — `analytics/combo.py`

**Input:** `transaction_baskets_basket_core.csv`, `dim_item.csv`, `feat_branch_item.csv`

**Approach:**
1. **Association rule mining** (Apriori or FP-Growth via `mlxtend`):
   - Convert `basket_core` → one-hot transaction matrix (basket_id × items).
   - Run with `min_support=0.05`, `min_confidence=0.3`, `min_lift=1.2`.
   - Output: top-N item pairs/triples by lift, per branch.
2. **Category-level combos**: aggregate items to `category` level (from `dim_item`) and re-run association rules → gives "coffee_hot + core_food" style combos.
3. **Attach-rate analysis** from `feat_branch_item.attach_tendency` → which items are add-on candidates.
4. **Final output**: ranked combo suggestions per branch with support, confidence, lift, and a "combo score" = lift × support.

**Modeling note:** 121 baskets across 3 branches is small. Confidence intervals will be wide. The module should report basket count per rule and flag rules with <10 supporting baskets as "indicative only."

**Key function signatures:**
- `find_combos(min_support, min_confidence, min_lift, top_n) → DataFrame`
- `find_category_combos(...) → DataFrame`
- `get_attach_candidates(top_n) → DataFrame`

---

### 2B. Demand Forecasting — `analytics/forecast/`

**Input:** `monthly_sales.csv`, `feat_branch_month.csv`, `dim_branch.csv`

**Approach — two complementary methods:**

1. **Ensemble estimator (primary)** — given only 4–5 data points per branch, a full ARIMA/Prophet is inappropriate. Instead, blend three simple estimators:
   - **Naïve last-value**: assume next month = last observed month.
   - **Weighted moving average (WMA-3)**: from `feat_branch_month.revenue_ma3`.
   - **Linear trend**: OLS on `month_num` → `revenue`.
   - Final estimate = **median of the three** (more robust than any single method on tiny history).
   - Confidence band derived from `feat_branch_month.volatility`.
   - Flag `is_partial_history` branches (Main Street Coffee) with wider uncertainty.

2. **Branch similarity model (secondary)** — for branches with less data:
   - Compute similarity between branches using channel mix (`dim_branch`), beverage share, and growth trajectory from `feat_branch_month`.
   - Transfer trend from the most similar longer-history branch, scaled by revenue ratio.

3. **Output**: per-branch monthly forecast table framed as a **demand index** (not a revenue forecast — all values are in internal scaled units):
   - `demand_index_forecast` — the ensemble point estimate.
   - `expected_change_vs_last_month` — percentage shift.
   - `relative_band_low`, `relative_band_high` — uncertainty range.
   - `method` — which estimator(s) contributed.
   - `confidence_level` — `low` / `medium` / `high` based on data availability.
   - All outputs clearly labeled **"internal scaled units only — not financial forecasts."**

**Why not Prophet/ARIMA:** 4–5 points. Overfitting guaranteed. The plan explicitly states this trade-off in the executive brief — it demonstrates ML rigor by *not* using a complex model when data doesn't support it.

**Key function signatures:**
- `forecast_branch(branch, periods_ahead=3) → DataFrame`
- `forecast_all(periods_ahead=3) → DataFrame`

---

### 2C. Expansion Feasibility — `analytics/expand.py`

**Input:** `monthly_sales.csv`, `avg_sales_menu.csv`, `dim_branch.csv`, `feat_branch_month.csv`, `feat_branch_shift.csv`, `feat_customer_delivery.csv`

**Approach — scoring framework + candidate location profiling:**

1. **Branch performance profiling:**
   - Revenue trajectory (growing/flat/declining) from `mom_growth`.
   - Channel efficiency: revenue per customer by channel from `avg_sales_menu`.
   - Delivery reach: customer count and repeat rate from `feat_customer_delivery`.
   - Staffing efficiency: revenue per valid shift hour from `feat_branch_shift` + `monthly_sales`.

2. **Expansion readiness index** per existing branch (0–100 composite):
   - Growth momentum (25%): positive `mom_growth`, low volatility.
   - Customer base strength (25%): repeat rate, lifespan, customer count.
   - Operational efficiency (25%): revenue per staff hour, low anomaly rate.
   - Channel diversification (25%): multiple active channels, balanced mix.

3. **Candidate location profiles** (not exact addresses — data-derived archetypes):
   - Based on highest-scoring existing branch's profile.
   - Output profiles such as: *"high-footfall takeaway corridor"*, *"dine-in neighborhood node"*, *"delivery-first hub"*.
   - Recommend channel mix, expected staffing level, menu focus for each profile.
   - Estimate break-even timeline using demand-index trajectory of closest analog branch.

4. **Optional external-enrichment path** (brief allows external data if documented):
   - User provides a list of candidate neighborhoods/locations with basic attributes (population density, rent tier, competitor count).
   - Module scores each candidate against the preferred branch archetype.
   - If no external data is provided, outputs profile recommendations only.

5. **Output**: branch scorecards + location profile recommendations + (if external data) scored candidate list.

**Key function signatures:**
- `score_branches() → DataFrame`
- `recommend_location_profiles() → list[dict]`
- `score_candidates(candidates: DataFrame) → DataFrame`  # optional external enrichment

---

### 2D. Shift Staffing Estimation — `analytics/staff.py`

**Input:** `attendance.csv`, `feat_branch_shift.csv`, `monthly_sales.csv`, `feat_branch_month.csv`

**Approach:**

1. **Demand-to-staff mapping:**
   - For branches with both attendance and revenue data, compute `demand_index_per_valid_shift_hour`.
   - Build a simple ratio: given forecasted demand index (from 2B), estimate required shift-hours.
   - Convert shift-hours → headcount using median shift duration from `feat_branch_shift.median_hours`.

2. **Banded output (lean / base / peak)** — because sales data is monthly and attendance is partial, a single exact headcount would overstate precision:
   - **Lean**: minimum viable staff (10th percentile of observed ratio).
   - **Base**: median-based estimate (recommended default).
   - **Peak**: capacity for high-demand periods (90th percentile).
   - Example output: `morning shift → 2 / 3 / 4 staff`.

3. **Shift-type distribution model:**
   - From `feat_branch_shift`: morning/afternoon/evening percentages.
   - Apply distribution to total required shifts → shifts needed per type per day.
   - Weekend adjustment using `weekend_shift_pct`.

4. **Anomaly-aware scheduling:**
   - Filter on `is_valid_shift=True` for all baseline calculations.
   - Report the anomaly rate and recommend management review if >15%.

5. **Cross-branch transfer** for Conut main (no attendance data):
   - Use revenue similarity to assign staffing profile from closest branch via `dim_branch`.
   - **Label clearly as "transferred estimate"** — not a directly observed staffing recommendation.

6. **Output**: per-branch, per-shift-type **staffing band table** (lean/base/peak) + weekly schedule template.

**Key function signatures:**
- `estimate_staffing(branch, forecast_demand_index=None) → dict`
- `estimate_all() → DataFrame`
- `generate_schedule(branch) → DataFrame`

---

### 2E. Coffee & Milkshake Growth Strategy — `analytics/growth.py`

**Input:** `items_by_group.csv`, `feat_branch_item.csv`, `dim_item.csv`, `avg_sales_menu.csv`, `transaction_baskets_basket_core.csv`

**Approach:**

1. **Current state analysis:**
   - Filter `dim_item` for `beverage_flag=True` → segment by `category` (coffee_hot, coffee_cold, milkshake).
   - Per branch: beverage share of total mix, rank distribution, top/bottom performers.
   - Benchmark each branch against the fleet average.

2. **Growth levers identification:**
   - **Under-indexed branches**: branches where beverage share is below fleet average → biggest growth opportunity.
   - **High-attach items**: from `feat_branch_item.attach_tendency` — beverages that naturally pair with food.
   - **Cross-sell candidates**: from combo analysis (2A) — food items that co-occur with beverages in baskets → suggest bundling.
   - **High-volume delivery branches**: from `avg_sales_menu` — branches where delivery is the dominant channel are natural targets for beverage promotions (we know channel volume but *not* beverage-by-channel breakdown; the logic is: if a branch is delivery-heavy and overall beverage-light, focus promo effort there).

3. **Actionable recommendations matrix:**
   - Per branch × per beverage category: current share → target share → specific action (bundle, promo, menu placement).
   - Prioritized by estimated impact (branch revenue × share gap).

4. **Output**: growth opportunity table + prioritized action list.

**Key function signatures:**
- `analyze_beverage_state() → DataFrame`
- `identify_growth_levers() → DataFrame`
- `recommend_actions() → list[dict]`

---

## 3. Layer 2 — Agent Core (`agent/`)

This is the "Chief of Operations Agent" — an LLM-backed reasoning layer that translates natural language questions into analytics calls.

### 3A. Tool Registry — `agent/tools.py`

Each analytics module (2A–2E) is wrapped as a **callable tool** with:
- A name: `combo_optimizer`, `demand_forecaster`, `expansion_analyzer`, `shift_planner`, `beverage_growth_strategist`
- A description string (for the LLM's tool-use prompt)
- Input parameters (branch name, time horizon, etc.)
- Output: structured result (tools call `analytics/*.run()` and return raw data; formatting is handled by the formatter)

Additionally, **data lookup tools**:
- `lookup_branch_info(branch)` → pulls from `dim_branch`
- `lookup_item_info(item)` → pulls from `dim_item`
- `check_data_quality(branch)` → pulls from `fact_reconciliation_checks`
- `get_kpis(branch)` → aggregates key metrics across feature tables

### 3B. Formatter — `agent/formatter.py`

All natural-language rendering lives here — **not inside analytics modules**. This keeps business logic and presentation cleanly separated.

- One `format_*()` function per tool: `format_combo_results()`, `format_forecast()`, etc.
- Accepts structured output (DataFrame/dict) → returns human-readable summary string.
- The agent engine calls the formatter after receiving tool results, before synthesizing the final answer.
- Benefits: easier testing, easier debugging, less duplication, single place to change output tone/style.

### 3C. Fallback Router — `agent/router.py`

A **rule-based intent classifier** that works without the LLM. Ensures the system remains functional even if the LLM API is unavailable or slow.

| Keywords | Routed To |
|---|---|
| `combo`, `bundle`, `pair`, `together` | `combo_optimizer` |
| `forecast`, `next month`, `demand`, `predict` | `demand_forecaster` |
| `expand`, `new branch`, `open`, `location` | `expansion_analyzer` |
| `staff`, `shift`, `schedule`, `employee` | `shift_planner` |
| `coffee`, `milkshake`, `beverage`, `growth` | `beverage_growth_strategist` |
| `quality`, `reconcil`, `trust` | `check_data_quality` |

**Usage:** LLM handles multi-tool reasoning and synthesis (primary path). If LLM API fails, the router dispatches to a single tool based on keyword match and returns the formatted output directly.

### 3D. System Prompt — `agent/prompts.py`

A carefully crafted system prompt that:
- Establishes the agent's role: "You are the Chief of Operations AI for Conut bakery."
- Lists available tools and when to use each.
- Encodes the **source-of-truth hierarchy** (so the LLM doesn't hallucinate data relationships).
- Includes **data limitations** (4–5 months, scaled units, 3/4 branch coverage for attendance/baskets).
- Instructs the agent to always cite which data source backs each claim.
- Instructs the agent to express uncertainty when data is thin.

### 3E. Agent Engine — `agent/engine.py`

A lightweight orchestration loop:

```
User query
    → router.py classifies intent (fallback path)
    → LLM decides which tool(s) to call (primary path)
    → Tool executes analytics function (or reads from artifacts/)
    → formatter.py renders result as natural language
    → LLM synthesizes answer with citations
    → Response to user
```

**Implementation options (pick one):**

| Option | Pros | Cons |
|---|---|---|
| **LangChain agent** | Mature tool-use, memory, chains | Heavy dependency, can be opaque |
| **Raw OpenAI/Anthropic function-calling** | Lightweight, transparent, full control | More manual wiring |
| **LangGraph** | Stateful multi-step reasoning, retries | Steeper learning curve |

**Recommendation:** Raw function-calling (OpenAI or Anthropic SDK) with a simple while-loop agent. Minimal dependencies, easy to debug, fully reproducible. Add a `conversation_history` list for multi-turn context.

**Multi-tool queries:** The agent should be able to chain tools. Example: "Should we open a new branch?" → calls `demand_forecaster` + `expansion_analyzer` + `shift_planner` → synthesizes.

---

## 4. Layer 2½ — Service Layer (`service/`)

A thin API layer between the Agent and any external consumer (OpenClaw, CLI, local web UI). Keeps OpenClaw as a pure adapter — not the core runtime.

### 4A. Service Router — `service/router.py`

- `handle_request(user_message: str, mode: str = "agent") → dict` — main entry point.
- `mode="agent"` → full LLM agent path via `agent/engine.py`.
- `mode="direct"` → keyword-based fallback via `agent/router.py` (no LLM needed).
- Returns a standardized **response contract** (see below).

### 4B. Contracts — `service/contracts.py`

Defines the response schema that all consumers receive:

```python
{
    "answer": str,           # Natural language response
    "evidence": list[dict],  # [{source, metric, value}, ...]
    "confidence": str,       # "high" / "medium" / "low"
    "limitations": list[str] # Active data caveats
}
```

This is slightly richer than `sources_used` alone — `evidence` + `limitations` maps to how judges evaluate claims.

### 4C. Cache — `service/cache.py` (optional)

- LRU or TTL cache for repeated queries during demo.
- Falls back to `artifacts/` precomputed results for known query patterns.

---

## 5. Layer 3 — OpenClaw Integration (`openclaw/`)

**OpenClaw** is the mandatory integration target. It is a **pure adapter** — all logic lives in the service layer.

### 5A. Integration Pattern

```
OpenClaw (UI/API)                          CLI / Local API
    ↓ sends user query                         ↓
openclaw/handlers.py                    service/router.py
    ↓ routes to service layer                  ↓
service/router.py                       agent/engine.py
    ↓                                          ↓
agent/engine.py                         (same path)
    ↓ returns response contract
openclaw/handlers.py
    ↓ formats for OpenClaw display
OpenClaw (displays to user)
```

Both OpenClaw and CLI hit the same `service/router.py` — the system is demo-safe even if OpenClaw is unavailable.

### 5B. Configuration — `openclaw/config.yaml`

- Agent name, description, version
- Available capabilities (maps to the 5 objectives)
- API keys / model configuration
- Data directory path

### 5C. Handlers — `openclaw/handlers.py`

- `handle_query(user_message: str) → str` — delegates to `service/router.py`
- Thin wrapper: error handling, logging, OpenClaw-specific response formatting
- Returns the service layer's response contract (answer, evidence, confidence, limitations)

### 5D. Example Queries to Demonstrate

| Query | Expected Tool Chain | Output Type |
|---|---|---|
| "What are the best combos for Conut Jnah?" | `combo_optimizer(branch="Conut Jnah")` | Ranked combo list |
| "What's the demand outlook for next month?" | `demand_forecaster(periods=1)` | Demand index table |
| "Should we open a 5th branch?" | `expansion_analyzer()` + `demand_forecaster()` | Scorecard + location profile |
| "How many staff for morning shifts at Tyre?" | `shift_planner(branch="Conut - Tyre", shift="morning")` | Staffing band (lean/base/peak) |
| "How can we grow milkshake sales?" | `beverage_growth_strategist(category="milkshake")` | Action list by branch |
| "What's the data quality situation?" | `check_data_quality()` | Reconciliation summary |

---

## 6. Layer 4 — Delivery & Demo (`docs/`)

### 6A. Repository Structure (Final)

```
Conut-AI-Operations/
├── README.md                      # Business problem, approach, how to run, key results
├── requirements.txt               # Pinned dependencies
├── .env.example                   # API key template
│
├── pipelines/                     # Layer 0 — Data ETL (DONE)
│   ├── README.md
│   ├── DOCUMENTATION.md
│   ├── run_pipeline.py
│   ├── output/                    # 15 clean CSVs
│   └── parsers/
│
├── analytics/                     # Layer 1 — Decision Engines
│   ├── __init__.py
│   ├── combo.py
│   ├── forecast/
│   │   ├── __init__.py
│   │   ├── trend.py               # Naïve + WMA + Linear ensemble
│   │   └── similarity.py          # Cross-branch transfer
│   ├── expand.py
│   ├── staff.py
│   └── growth.py
│
├── artifacts/                     # Materialized analytics cache
│   └── analytics/
│       ├── combo_results.json
│       ├── forecast_results.csv
│       ├── expansion_scorecards.csv
│       ├── staffing_templates.csv
│       └── growth_actions.json
│
├── agent/                         # Layer 2 — Agent Core
│   ├── __init__.py
│   ├── tools.py                   # Tool definitions
│   ├── formatter.py               # NL rendering (separated from analytics)
│   ├── router.py                  # Rule-based fallback intent classifier
│   ├── prompts.py                 # System prompt
│   └── engine.py                  # Agent loop
│
├── service/                       # Layer 2½ — Service API
│   ├── __init__.py
│   ├── router.py                  # Main entry point for all consumers
│   ├── contracts.py               # Response schema definition
│   └── cache.py                   # Optional query cache
│
├── openclaw/                      # Layer 3 — OpenClaw adapter
│   ├── config.yaml
│   └── handlers.py
│
├── docs/                          # Layer 4 — Delivery
│   ├── executive_brief.pdf        # 2-page PDF
│   ├── architecture.md            # This plan
│   └── demo/
│       ├── screenshots/
│       └── demo_queries.md        # Scripted demo walkthrough
│
└── tests/                         # Validation
    ├── test_combo.py
    ├── test_forecast.py
    ├── test_agent.py
    ├── test_data_contracts.py     # Validates service response schema
    └── test_openclaw_handler.py   # OpenClaw adapter integration test
```

### 6B. Executive Brief Structure (2 pages)

- **Page 1**: Problem framing, data overview (4 branches, 15 clean datasets, 4–5 months), approach (pattern-based ETL → analytics → LLM agent → OpenClaw).
- **Page 2**: Top findings per objective (1–2 lines each), recommended actions, expected impact, risks & limitations, "what we'd do with more data."

### 6C. Demo Script

A scripted sequence of 6–8 OpenClaw queries covering all 5 objectives, showing the agent reasoning through multi-step queries, citing data sources, and expressing appropriate uncertainty.

---

## 7. Dependency Stack

| Package | Purpose | Layer |
|---|---|---|
| `pandas`, `numpy` | Data manipulation | 0, 1 |
| `mlxtend` | Apriori / FP-Growth | 1 (combo) |
| `scikit-learn` | Linear regression, clustering | 1 (forecast, expand) |
| `scipy` | Confidence intervals | 1 (forecast) |
| `openai` or `anthropic` | LLM API for agent | 2 |
| `pyyaml` | Config parsing | 3 |
| `python-dotenv` | API key management | 2, 3 |
| OpenClaw SDK/CLI | Integration target | 3 |

No heavy ML frameworks (PyTorch, TensorFlow) — the data doesn't justify them.

---

## 8. Data Coverage Matrix

This maps which pipeline outputs feed which objective, ensuring nothing is missed:

| Output File | Combo | Forecast | Expansion | Staffing | Growth |
|---|---|---|---|---|---|
| `monthly_sales` | | **primary** | **primary** | input | |
| `items_by_group` | reference | | | | **primary** |
| `avg_sales_menu` | | | input | | input |
| `customer_orders` | | | input | | |
| `basket_core` | **primary** | | | | input |
| `attendance` | | | | **primary** | |
| `dim_branch` | | input | input | input | input |
| `dim_item` | input | | | | input |
| `reconciliation` | | | reference | | |
| `feat_branch_month` | | **primary** | input | input | |
| `feat_branch_item` | input | | | | **primary** |
| `feat_customer_delivery` | | | input | | |
| `feat_branch_shift` | | | input | **primary** | |

---

## 9. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 121 baskets too few for reliable Apriori | High | Combo rules have low confidence | Report support counts, flag thin rules, use category-level fallback |
| 4–5 months insufficient for seasonality | Certain | No seasonal decomposition possible | Use trend + momentum only, state limitation clearly |
| Scaled units mislead downstream models | Medium | Absolute predictions meaningless | All models output demand indices, ratios, ranks — never absolute LBP |
| Conut main missing from attendance + baskets | Certain | 1/4 branches has no staffing/combo data | Cross-branch transfer via similarity, label as "transferred estimate" |
| LLM hallucination in agent responses | Medium | Wrong recommendations | Strict tool-use pattern (agent can ONLY use tool outputs), source citation required |
| LLM API unavailable during demo | Medium | Agent non-functional | Rule-based fallback router (`agent/router.py`) + precomputed artifacts |
| OpenClaw API changes or instability | Low | Integration breaks at demo | Pin SDK version, service layer enables CLI fallback |
| Staffing estimates over-precise | Medium | False confidence in headcount | Output as lean/base/peak bands, not single numbers |

---

## 10. Implementation Order (Suggested)

| Phase | Work | Estimated Effort | Depends On |
|---|---|---|---|
| **Phase 1** | `analytics/combo.py` + `analytics/growth.py` | 2–3 hours | Layer 0 (done) |
| **Phase 2** | `analytics/forecast/` + `analytics/staff.py` | 2–3 hours | Layer 0 (done) |
| **Phase 3** | `analytics/expand.py` | 1–2 hours | Phase 2 (needs forecast) |
| **Phase 4** | `artifacts/` materialization + `service/` layer | 1–2 hours | Phases 1–3 |
| **Phase 5** | `agent/tools.py` + `agent/formatter.py` + `agent/router.py` + `agent/engine.py` | 2–3 hours | Phase 4 |
| **Phase 6** | `openclaw/` integration (adapter only) | 1 hour | Phase 5 |
| **Phase 7** | `docs/` — README, executive brief, demo | 1–2 hours | Phase 6 |

Phases 1 & 2 are independent and can be parallelized if working in a team.
Phase 4 (service + artifacts) is a new layer — lightweight but critical for demo stability.

---

## 11. Key Design Decisions (Summary)

1. **No deep learning / Prophet / ARIMA** — 4–5 data points per branch. Ensemble of simple estimators (naïve + WMA + linear) with honest uncertainty bands is more rigorous.
2. **Association rules over collaborative filtering** — basket data is sparse (121 baskets), Apriori with category fallback is appropriate.
3. **Location profiles over geo-ML for expansion** — no external location data by default. Output candidate location archetypes; optionally score user-provided candidates if external data is supplied.
4. **Raw function-calling over LangChain** — minimal dependencies, transparent agent behavior, easier to debug and demo.
5. **Strict separation of computation and presentation** — analytics modules return structured data only; `agent/formatter.py` handles all natural-language rendering. Independently testable, debuggable, and maintainable.
6. **Service layer decouples OpenClaw** — OpenClaw is a pure adapter; the same system is demoable via CLI or local API if OpenClaw is unavailable.
7. **Banded outputs for uncertain estimates** — staffing uses lean/base/peak bands; forecasts use relative demand indices with confidence levels. No false precision.
8. **Materialized artifacts for demo stability** — precomputed results in `artifacts/` ensure reproducible screenshots and fast demos; live recomputation available on demand.
9. **Fallback router for LLM independence** — rule-based intent classification in `agent/router.py` ensures basic functionality without LLM API access.
10. **Source-of-truth hierarchy enforced at every layer** — the system prompt, tool descriptions, and documentation all reinforce which data to trust for which metric.
