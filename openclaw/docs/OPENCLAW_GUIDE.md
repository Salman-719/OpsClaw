# OpenClaw Setup Guide — From Zero to Running Agent

Complete guide to install, configure, and run the **OpsClaw** agent using OpenClaw with a Telegram bot interface.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Install OpenClaw](#2-install-openclaw)
3. [Initial Setup (Doctor Wizard)](#3-initial-setup-doctor-wizard)
4. [Configure the LLM Provider](#4-configure-the-llm-provider)
5. [Set the Agent Workspace](#5-set-the-agent-workspace)
6. [Create a Telegram Bot](#6-create-a-telegram-bot)
7. [Add the Telegram Channel](#7-add-the-telegram-channel)
8. [Configure Session Isolation](#8-configure-session-isolation)
9. [Create BOOTSTRAP.md (System Prompt)](#9-create-bootstrapmd-system-prompt)
10. [Create a Custom Skill](#10-create-a-custom-skill)
11. [Pre-Compute Analytics Outputs](#11-pre-compute-analytics-outputs)
12. [Start the Gateway](#12-start-the-gateway)
13. [Test on Telegram](#13-test-on-telegram)
14. [Architecture Overview](#14-architecture-overview)
15. [Configuration Reference](#15-configuration-reference)
16. [Troubleshooting](#16-troubleshooting)

---

## 1. Prerequisites

| Requirement | Version | Why |
|---|---|---|
| **Node.js** | 22+ | OpenClaw runtime |
| **npm** | Comes with Node.js | Install OpenClaw globally |
| **Python** | 3.9+ | Run analytics pipelines |
| **OpenAI API key** | — | LLM backend (GPT-4o) |
| **Telegram account** | — | Create a bot via @BotFather |

### Check Node.js and npm

```bash
node --version    # Should show v22.x.x or higher
npm --version     # Should show 10.x.x or higher
```

If not installed, download from [nodejs.org](https://nodejs.org/).

---

## 2. Install OpenClaw

### npm (All platforms — recommended)

```bash
npm install -g openclaw
```

### Verify installation

```bash
openclaw --version
# Expected: OpenClaw 2026.x.x
```

### Also install clawhub (skill marketplace CLI)

```bash
npm install -g clawhub
```

---

## 3. Initial Setup (Doctor Wizard)

Run the built-in doctor to initialize default config:

```bash
openclaw doctor --fix
```

This creates `~/.openclaw/openclaw.json` with default settings. On Windows, this is at `%USERPROFILE%\.openclaw\openclaw.json`.

> **Important:** `doctor --fix` may overwrite custom settings if run again later. After initial setup, use `openclaw config set` commands to modify config.

---

## 4. Configure the LLM Provider

OpenClaw needs an LLM to power the agent. We use **OpenAI GPT-4o**.

### Authenticate with OpenAI

Pipe your API key into the auth command:

**Windows (PowerShell):**
```powershell
"sk-proj-YOUR_API_KEY_HERE" | openclaw models auth paste-token --provider openai
```

**macOS / Linux (Bash):**
```bash
echo "sk-proj-YOUR_API_KEY_HERE" | openclaw models auth paste-token --provider openai
```

### Set the default model

```bash
openclaw config set agents.defaults.model.primary openai/gpt-4o
```

### Verify

```bash
openclaw config get agents.defaults.model.primary
# Should output: openai/gpt-4o
```

> **Note:** The API key is stored in `~/.openclaw/agents/main/agent/auth-profiles.json`, NOT in the main config. Never commit this file.

---

## 5. Set the Agent Workspace

The workspace tells OpenClaw which directory the agent can read files from. This is where your analytics outputs, BOOTSTRAP.md, and skills live.

```bash
openclaw config set agents.defaults.workspace "/absolute/path/to/OpsClaw"
```

**Windows example:**
```powershell
openclaw config set agents.defaults.workspace "C:\Users\YourName\path\to\OpsClaw"
```

The agent gets `read` tool access to this directory and all subdirectories.

---

## 6. Create a Telegram Bot

1. Open Telegram and message **[@BotFather](https://t.me/BotFather)**
2. Send `/newbot`
3. Follow the wizard — choose a display name and username
4. BotFather gives you an **HTTP API token** like: `123456789:AAH-abcdef...xyz`
5. **Copy this token** — you'll need it in the next step

> Do NOT share or commit the bot token. Treat it like a password.

---

## 7. Add the Telegram Channel

### Register the bot token

```bash
openclaw channels add telegram --token "YOUR_BOT_TOKEN_HERE"
```

### Allow DMs from anyone

```bash
openclaw config set channels.telegram.dmPolicy open
```

### Allow all users (or restrict to specific Telegram IDs)

**Windows PowerShell:**
```powershell
openclaw config set --json channels.telegram.allowFrom '[\"*\"]'
```

**macOS / Linux Bash:**
```bash
openclaw config set --json channels.telegram.allowFrom '["*"]'
```

### Disable streaming (recommended for Telegram)

```bash
openclaw config set channels.telegram.streaming off
```

### Verify

```bash
openclaw config get channels.telegram.enabled
# Should output: true
```

---

## 8. Configure Session Isolation

By default, all Telegram DMs share one session. Set per-user sessions:

```bash
openclaw config set session.dmScope per-channel-peer
```

---

## 9. Create BOOTSTRAP.md (System Prompt)

Create a file called `BOOTSTRAP.md` in the **workspace root** (the directory you set in Step 5). This is automatically loaded as the agent's system prompt for every conversation.

**File: `OpsClaw/BOOTSTRAP.md`**

```markdown
# Conut Bakery — Chief of Operations Agent

You are **OpsClaw**, the AI Chief of Operations for Conut Bakery chain
(4 branches: Conut, Conut Jnah, Conut Tyre, Main Street Coffee).

## CRITICAL RULE: You already have all the data. NEVER ask the user for files.

All analytics are pre-computed and stored in this workspace. When the user asks
a question, use the `read` tool to open the relevant output file listed below.
Do NOT invent file paths — only use the exact paths listed here.

## Exact File Paths

### Combos (menu item pairings)
- `analytics/combo/data/artifacts/combo_pairs_explained.csv`

### Demand Forecasting
- `analytics/forecast/output/demand_forecast_all.csv`

### Branch Expansion
- `analytics/expansion/output/recommendation.json`
- `analytics/expansion/output/feasibility_scores.csv`
- `analytics/expansion/output/branch_kpis.csv`

### Staffing
- `analytics/staffing/output/branch_summary_view.csv`
- `analytics/staffing/output/staffing_gap_hourly.csv`
- `analytics/staffing/output/top_gap_slots.csv`
- `analytics/staffing/output/branch_staffing_findings.csv`

### Beverage Growth (coffee & milkshake)
- `analytics/growth/output/branch_beverage_kpis.csv`
- `analytics/growth/output/branch_growth_potential.csv`
- `analytics/growth/output/recommendation.json`
- `analytics/growth/output/assoc_rules_by_branch.csv`

## How to Answer
1. Classify the question (combos / forecast / expansion / staffing / beverages)
2. Use the `read` tool to open the EXACT file path from the list above
3. Parse the CSV/JSON and extract relevant data
4. Reply: direct answer → 2-4 data points → one actionable takeaway
5. Keep replies under 300 words. Use *bold* and numbered lists (Telegram format).

## NEVER DO THIS
- Never say "I don't have the data" or "please upload a file"
- Never invent file paths not listed above
- Never ask what system the user uses — you know it's Conut Bakery
```

> **How it works:** OpenClaw detects `BOOTSTRAP.md` in the workspace root and injects it as the system prompt. Run `openclaw status` to verify — look for "1 bootstrap file present".

---

## 10. Create a Custom Skill

Skills are `SKILL.md` files that provide domain-specific instructions to the agent. They activate when the user's question matches their trigger keywords.

### Directory structure

```
OpsClaw/
└── skills/
    └── conut-ops-agent/
        └── SKILL.md
```

Create the directory:

```bash
mkdir -p skills/conut-ops-agent
```

**Windows PowerShell:**
```powershell
New-Item -Path "skills\conut-ops-agent" -ItemType Directory -Force
```

### Create SKILL.md

**File: `OpsClaw/skills/conut-ops-agent/SKILL.md`**

The skill file uses YAML frontmatter for metadata and markdown for instructions:

````markdown
---
name: conut-ops-agent
description: >
  Conut Bakery Chief of Operations AI Agent. Handles questions about branch
  performance, sales, staffing, combos, beverages, demand forecasting, and
  branch expansion. Covers five business objectives:
  (1) Combo Optimization (2) Demand Forecasting (3) Branch Expansion
  (4) Staffing Estimation (5) Coffee & Milkshake Growth Strategy.
  Trigger on: sales, branch, staffing, scheduling, combos, menu, beverage,
  expansion, demand, forecast, KPI, underperforming, growth potential.
---

# Conut Ops Agent

You are the Chief of Operations Agent for **Conut Bakery**.

## Question Classification

| Objective | Keywords |
|-----------|----------|
| 1 - Combos | combo, pairing, bundle, cross-sell, "goes with" |
| 2 - Forecast | forecast, predict, demand, next month, trend |
| 3 - Expansion | expand, new branch, feasibility, region |
| 4 - Staffing | staff, schedule, shift, gap, understaffed |
| 5 - Growth | beverage, coffee, milkshake, attachment rate |

## Data File Paths

(Same paths as listed in BOOTSTRAP.md — refer to Section 9)

## Response Format
- Lead with the direct answer
- Include 2-4 supporting data points
- End with one actionable takeaway
- Keep under 300 words for Telegram
````

> **How skills work:** OpenClaw scans `skills/*/SKILL.md` in the workspace at startup. The skill appears as a `/conut_ops_agent` command in Telegram. The agent also activates it automatically when keywords match.

---

## 11. Pre-Compute Analytics Outputs

The agent reads pre-computed CSV/JSON files — it does NOT run Python at query time. Generate all outputs before starting the gateway:

```bash
cd OpsClaw
python infra/local_test.py
```

This runs all 5 analytics pipelines and writes outputs to:

```
analytics/combo/data/artifacts/         → combo_pairs_explained.csv
analytics/expansion/output/             → branch_kpis.csv, feasibility_scores.csv, recommendation.json
analytics/forecast/output/              → demand_forecast_all.csv, per-branch CSVs
analytics/growth/output/                → branch_beverage_kpis.csv, branch_growth_potential.csv, recommendation.json
analytics/staffing/output/              → branch_summary_view.csv, staffing_gap_hourly.csv, top_gap_slots.csv
```

### Verify outputs exist

```bash
ls analytics/*/output/
ls analytics/combo/data/artifacts/
```

---

## 12. Start the Gateway

```bash
openclaw gateway run --auth none --verbose
```

**Expected output:**
```
🦞 OpenClaw 2026.x.x
[gateway] agent model: openai/gpt-4o
[gateway] listening on ws://127.0.0.1:18789
[telegram] [default] starting provider (@yourbotname)
[skills] Sanitized skill command name "conut-ops-agent" to "/conut_ops_agent".
```

Key things to verify:
- ✅ No `409 Conflict` errors (means no other instance is running)
- ✅ Telegram provider starts with your bot username
- ✅ `conut-ops-agent` skill is listed

> **Keep this terminal open.** The gateway runs in the foreground.

---

## 13. Test on Telegram

### Verify health first

Open a **new terminal** (keep gateway running):

```bash
openclaw health
```

**Expected:**
```
Telegram: ok (@yourbotname) (xxxms)
Agents: main (default)
```

### Check bootstrap loaded

```bash
openclaw status
```

Look for: `1 bootstrap file present`

### Send test messages

Open Telegram, find your bot by username, and send:

| Message | Expected behavior |
|---|---|
| `hello` | Agent introduces itself as OpsClaw |
| `Which branches are underperforming in coffee sales?` | Reads `branch_beverage_kpis.csv`, returns rankings |
| `What are the best-selling combos?` | Reads `combo_pairs_explained.csv`, returns top pairs |
| `Should we open a new branch?` | Reads `recommendation.json`, returns feasibility analysis |
| `/conut_ops_agent Which branch is understaffed?` | Explicit skill invocation |

---

## 14. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Your Machine                               │
│                                                                 │
│  ┌──────────────┐    ┌───────────────────┐    ┌──────────────┐ │
│  │   Telegram    │◄──►│  OpenClaw Gateway  │◄──►│   OpenAI     │ │
│  │   Bot API     │    │  (ws://127.0.0.1   │    │   GPT-4o     │ │
│  │              │    │   :18789)           │    │   API        │ │
│  └──────────────┘    └─────────┬──────────┘    └──────────────┘ │
│                                │                                │
│                    ┌───────────▼──────────┐                     │
│                    │  Workspace (OpsClaw/) │                     │
│                    │                      │                     │
│                    │  BOOTSTRAP.md        │  ← system prompt    │
│                    │  skills/SKILL.md     │  ← domain skill     │
│                    │  analytics/*/output/ │  ← pre-computed     │
│                    │    *.csv, *.json     │     data files      │
│                    └─────────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘

Flow:
1. User sends message on Telegram
2. OpenClaw gateway receives it via long-polling
3. Gateway loads BOOTSTRAP.md + SKILL.md as system prompt context
4. Sends prompt + message to OpenAI GPT-4o
5. GPT-4o uses `read` tool to access analytics CSV/JSON files in workspace
6. GPT-4o generates data-driven response
7. Gateway sends response back to Telegram user
```

### Key concepts

| Concept | What it is |
|---|---|
| **Gateway** | Long-running process that bridges Telegram ↔ LLM agent |
| **BOOTSTRAP.md** | Always-loaded system prompt in workspace root |
| **Skill (SKILL.md)** | Domain-specific instructions in `skills/<name>/SKILL.md` |
| **Workspace** | Directory the agent can read files from via `read` tool |
| **Session** | Conversation state per user (stored in `~/.openclaw/agents/main/sessions/`) |

### What skills are NOT

Skills are **NOT** HTTP endpoints or webhooks. They are markdown instruction files that get injected into the LLM prompt when relevant. The agent reads data files directly from the workspace filesystem — no separate server needed.

---

## 15. Configuration Reference

All config is managed via CLI. The config file lives at `~/.openclaw/openclaw.json`.

### View / modify config

```bash
openclaw config get <key>                           # Read a value
openclaw config set <key> <value>                   # Set a scalar
openclaw config set --json <key> '<json_value>'     # Set array/object
```

### Key settings

| Setting | CLI command | Purpose |
|---|---|---|
| LLM model | `openclaw config set agents.defaults.model.primary openai/gpt-4o` | Which model to use |
| Workspace | `openclaw config set agents.defaults.workspace "/path/to/OpsClaw"` | Agent file access |
| Telegram DM policy | `openclaw config set channels.telegram.dmPolicy open` | Allow DMs |
| Telegram allow list | `openclaw config set --json channels.telegram.allowFrom '["*"]'` | Who can DM |
| Session scope | `openclaw config set session.dmScope per-channel-peer` | Per-user sessions |
| Gateway mode | `openclaw config set gateway.mode local` | Local gateway |

### Useful commands

```bash
openclaw --version          # Version info
openclaw doctor             # Check for config issues
openclaw health             # Check Telegram + agent health
openclaw status             # Detailed status (sessions, bootstrap, model)
openclaw skills list        # List bundled skills
openclaw gateway run        # Start gateway (foreground)
```

### File locations

| File | Location | Purpose |
|---|---|---|
| Main config | `~/.openclaw/openclaw.json` | All settings |
| Auth profiles | `~/.openclaw/agents/main/agent/auth-profiles.json` | API keys |
| Sessions | `~/.openclaw/agents/main/sessions/` | Conversation history |
| Logs | `$TMPDIR/openclaw/openclaw-YYYY-MM-DD.log` | Gateway logs |

---

## 16. Troubleshooting

### 409 Conflict: terminated by other getUpdates request

**Cause:** Another gateway (or node process) is polling the same Telegram bot.

**Fix:**
```bash
# Kill all node processes
# Windows:
Stop-Process -Name node -Force
# macOS/Linux:
killall node

# Reset Telegram polling state
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"

# Wait 5 seconds, then restart gateway
sleep 5
openclaw gateway run --auth none --verbose
```

### Bot says "I don't have the data" or asks for file uploads

**Cause:** BOOTSTRAP.md is missing or doesn't have explicit file paths.

**Fix:**
1. Verify BOOTSTRAP.md exists in workspace root
2. Check `openclaw status` — should show "1 bootstrap file present"
3. Check `openclaw config get agents.defaults.workspace` — must point to the directory containing BOOTSTRAP.md
4. Clear old sessions: delete `~/.openclaw/agents/main/sessions/*.jsonl` and `sessions.json`
5. Restart gateway

### Model access error (e.g., "project does not have access to gpt-4o")

**Cause:** The OpenAI API key doesn't have access to the configured model.

**Fix:**
```bash
# Re-authenticate with a valid key
echo "sk-proj-NEW_KEY" | openclaw models auth paste-token --provider openai
```

### Gateway won't start

**Checklist:**
1. `openclaw doctor` — fix any reported issues
2. `channels.telegram.dmPolicy` must be `open`
3. `channels.telegram.allowFrom` must include `["*"]`
4. Telegram bot token must be registered via `openclaw channels add telegram --token "..."`

### Skill not loading

**Checklist:**
1. File must be at `<workspace>/skills/<skill-name>/SKILL.md`
2. Must have YAML frontmatter with `name` and `description`
3. Look for `[skills] Sanitized skill command name` in gateway startup logs
4. Try invoking directly: `/conut_ops_agent your question`

### Clear all sessions (fresh start)

```bash
# Windows:
Remove-Item "$env:USERPROFILE\.openclaw\agents\main\sessions\*" -Force

# macOS/Linux:
rm -rf ~/.openclaw/agents/main/sessions/*
```

Then restart the gateway.

---

## Quick Reference — Full Setup in 10 Commands

```bash
# 1. Install
npm install -g openclaw

# 2. Initialize
openclaw doctor --fix

# 3. Auth
echo "YOUR_OPENAI_KEY" | openclaw models auth paste-token --provider openai

# 4. Model
openclaw config set agents.defaults.model.primary openai/gpt-4o

# 5. Workspace
openclaw config set agents.defaults.workspace "/path/to/OpsClaw"

# 6. Telegram
openclaw channels add telegram --token "YOUR_BOT_TOKEN"
openclaw config set channels.telegram.dmPolicy open
openclaw config set --json channels.telegram.allowFrom '["*"]'

# 7. Sessions
openclaw config set session.dmScope per-channel-peer

# 8. Create BOOTSTRAP.md and skills/conut-ops-agent/SKILL.md (see Sections 9-10)

# 9. Generate analytics outputs
cd OpsClaw && python infra/local_test.py

# 10. Run
openclaw gateway run --auth none --verbose
```
