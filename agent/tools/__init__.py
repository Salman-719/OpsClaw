"""
Agent tool definitions — Bedrock Converse API toolSpec format.

Each tool has a name, description, and inputSchema that tells the LLM
what parameters it can pass.  The executor maps tool names → functions.
"""

from __future__ import annotations

TOOL_SPECS: list[dict] = [
    # ── 1. Forecast ──────────────────────────────────────────────────────
    {
        "toolSpec": {
            "name": "query_forecast",
            "description": (
                "Query the demand forecast for Conut branches. "
                "Can get a single forecast, list all for a branch, or compare all branches. "
                "Branches: Conut, Conut - Tyre, Conut Jnah, Main Street Coffee. "
                "Scenarios: base, optimistic.  Periods: 1 (1-month), 2 (2-month), 3 (3-month)."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "branch": {
                            "type": "string",
                            "description": "Branch name. Omit to compare all branches.",
                        },
                        "scenario": {
                            "type": "string",
                            "enum": ["base", "optimistic"],
                            "description": "Forecast scenario. Default: base.",
                        },
                        "period": {
                            "type": "integer",
                            "enum": [1, 2, 3],
                            "description": "Forecast horizon. 1=1-month ahead (most reliable). Default: 1.",
                        },
                        "compare": {
                            "type": "boolean",
                            "description": "If true, return primary forecasts for all branches side-by-side.",
                        },
                    },
                    "required": [],
                },
            },
        }
    },
    # ── 2. Combo Optimization ────────────────────────────────────────────
    {
        "toolSpec": {
            "name": "query_combos",
            "description": (
                "Query product combo / association analysis. "
                "Returns item pairs that are frequently bought together. "
                "Can filter by scope (overall, branch, channel) and minimum lift. "
                "Lift > 3 = strong association, > 5 = very strong."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "branch": {
                            "type": "string",
                            "description": "Branch name to filter combos. Omit for overall.",
                        },
                        "scope": {
                            "type": "string",
                            "description": "Exact scope string (e.g. 'overall', 'branch:Conut Jnah'). Overrides branch param.",
                        },
                        "min_lift": {
                            "type": "number",
                            "description": "Minimum lift threshold. Default: 1.0.",
                        },
                        "top_n": {
                            "type": "integer",
                            "description": "Max pairs to return. Default: 10.",
                        },
                    },
                    "required": [],
                },
            },
        }
    },
    # ── 3. Expansion Feasibility ─────────────────────────────────────────
    {
        "toolSpec": {
            "name": "query_expansion",
            "description": (
                "Query branch expansion feasibility analysis. "
                "Can return: branch KPIs, feasibility scores/rankings, or the expansion recommendation. "
                "Branches: batroun, bliss, jnah, tyre. "
                "Score tiers: High (>0.6), Medium (0.4-0.6), Low (<0.4)."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["kpi", "feasibility", "ranking", "recommendation", "all_kpis"],
                            "description": (
                                "What to retrieve: "
                                "'kpi' = operational KPIs for a branch, "
                                "'feasibility' = score + tier for a branch, "
                                "'ranking' = all branches ranked by feasibility, "
                                "'recommendation' = expansion recommendation, "
                                "'all_kpis' = KPIs for all branches."
                            ),
                        },
                        "branch": {
                            "type": "string",
                            "description": "Branch name (required for 'kpi' and 'feasibility').",
                        },
                    },
                    "required": ["query_type"],
                },
            },
        }
    },
    # ── 4. Staffing Estimation ───────────────────────────────────────────
    {
        "toolSpec": {
            "name": "query_staffing",
            "description": (
                "Query shift staffing estimation data. "
                "Can return: branch-level findings, hourly gap details, or worst gaps. "
                "Branches: Conut - Tyre, Conut Jnah, Main Street Coffee. "
                "Gap > 0 = understaffed, Gap < 0 = overstaffed."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["findings", "gaps", "worst_gaps", "all_findings", "top_gaps"],
                            "description": (
                                "'findings' = branch-level summary, "
                                "'gaps' = hourly gaps (optionally filtered by day), "
                                "'worst_gaps' = top N worst understaffed slots, "
                                "'all_findings' = all branches summary, "
                                "'top_gaps' = worst gaps across all branches."
                            ),
                        },
                        "branch": {
                            "type": "string",
                            "description": "Branch name (required for findings/gaps/worst_gaps).",
                        },
                        "day": {
                            "type": "string",
                            "enum": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                            "description": "Day of week filter for 'gaps' query.",
                        },
                        "top_n": {
                            "type": "integer",
                            "description": "Number of worst gaps to return. Default: 5.",
                        },
                    },
                    "required": ["query_type"],
                },
            },
        }
    },
    # ── 5. Growth Strategy ───────────────────────────────────────────────
    {
        "toolSpec": {
            "name": "query_growth",
            "description": (
                "Query coffee & milkshake growth strategy data. "
                "Includes beverage attachment rates, growth potential rankings, "
                "association rules (food→beverage bundles), and strategy recommendation. "
                "Branches: Conut - Tyre, Conut Jnah, Main Street Coffee."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["kpi", "potential", "ranking", "rules", "recommendation", "all_kpis"],
                            "description": (
                                "'kpi' = beverage KPIs for a branch, "
                                "'potential' = growth potential for a branch, "
                                "'ranking' = all branches by growth potential, "
                                "'rules' = association rules for a branch, "
                                "'recommendation' = overall growth strategy, "
                                "'all_kpis' = beverage KPIs for all branches."
                            ),
                        },
                        "branch": {
                            "type": "string",
                            "description": "Branch name (required for kpi/potential/rules).",
                        },
                        "min_lift": {
                            "type": "number",
                            "description": "Min lift filter for rules. Default: 1.0.",
                        },
                        "top_n": {
                            "type": "integer",
                            "description": "Max rules to return. Default: 10.",
                        },
                    },
                    "required": ["query_type"],
                },
            },
        }
    },
    # ── 6. Executive Overview ────────────────────────────────────────────
    {
        "toolSpec": {
            "name": "get_overview",
            "description": (
                "Get a cross-feature executive overview for Conut operations. "
                "Returns key metrics from all 5 analytics modules in one call: "
                "top forecast, best combos, expansion recommendation, staffing status, growth strategy."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
    },
    # ── 7. All Recommendations ───────────────────────────────────────────
    {
        "toolSpec": {
            "name": "get_all_recommendations",
            "description": (
                "Retrieve all strategic recommendations from every feature: "
                "expansion recommendation, growth strategy, staffing actions, and top combos. "
                "Use when asked for an overall operations summary or business advice."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
    },
]
