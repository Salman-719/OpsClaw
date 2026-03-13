# AI Agent Service

> FastAPI service that provides an AI-powered operations agent backed by AWS Bedrock (Claude Haiku 4.5) with tool-calling capabilities and DynamoDB data access.

---

## Overview

The agent service (`agent/`) is a **FastAPI** application that:

1. Receives natural-language questions via REST API
2. Routes them to **AWS Bedrock** (Claude Haiku 4.5) with a system prompt and tool definitions
3. Executes **tool calls** against DynamoDB to fetch real data
4. Returns grounded, data-backed answers with source tracing
5. Also serves **dashboard endpoints** for the React frontend
6. Manages **data upload** and pipeline triggering

## File Structure

```
agent/
├── main.py                  # FastAPI app entry point
├── config.py                # Environment-based configuration
├── Dockerfile               # Agent Docker image
├── requirements.txt         # Python dependencies
├── core/
│   ├── __init__.py          # System prompt (SYSTEM_PROMPT)
│   └── agent.py             # Bedrock Converse API + tool-calling loop
├── dynamo/
│   ├── __init__.py          # Shared DynamoDB helpers + local CSV fallback
│   ├── combo.py             # Feature 1 queries
│   ├── forecast.py          # Feature 2 queries
│   ├── expansion.py         # Feature 3 queries
│   ├── staffing.py          # Feature 4 queries
│   └── growth.py            # Feature 5 queries
├── models/
│   └── __init__.py          # Pydantic request/response schemas
├── routes/
│   ├── __init__.py          # POST /api/chat
│   ├── dashboard.py         # GET /api/dashboard/*
│   └── upload.py            # POST /api/upload/*
└── tools/
    ├── __init__.py          # 7 Bedrock tool specifications
    └── executor.py          # Tool name → function dispatcher
```

---

## Core Agent Loop (`core/agent.py`)

The agent uses the **Bedrock Converse API** with iterative tool-calling:

```
User Message
     │
     ▼
┌──────────────────┐
│  Bedrock Converse│ ← System prompt + tool specs
│ (Claude Haiku 4.5) │
└────────┬─────────┘
         │
    ┌────┴────┐
    │end_turn?│──Yes──► Return final text answer
    └────┬────┘
         │ No (tool_use)
         ▼
┌──────────────────┐
│  execute_tool()  │ ← DynamoDB query
└────────┬─────────┘
         │
         ▼ (tool results)
┌──────────────────┐
│  Bedrock Converse│ ← Continues reasoning with data
│  (next round)    │
└──────────────────┘
         │
    (repeat up to 10 rounds)
```

### Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `AWS_REGION` | `eu-west-1` | AWS region for all services |
| `BEDROCK_MODEL_ID` | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` | Claude model to use |
| `BEDROCK_MAX_TOKENS` | `4096` | Max response tokens |
| `BEDROCK_TEMPERATURE` | `0.1` | Low temperature for factual accuracy |
| `LOCAL_MODE` | `true` | If true, reads from local CSVs |
| `ENV_NAME` | `dev` | Environment name |
| `S3_DATA_BUCKET` | `conut-ops-data-dev` | S3 bucket for data |
| `STATE_MACHINE_ARN` | — | Step Functions ARN for pipeline trigger |

---

## Tools (7 Total)

The agent has 7 tools that Bedrock can call:

### 1. `query_forecast`
Query demand forecast data for branches.

| Parameter | Type | Description |
|-----------|------|-------------|
| `branch` | string | Branch name (optional — omit to list all) |
| `scenario` | string | `base` or `optimistic` |
| `period` | integer | 1, 2, or 3 month horizon |
| `compare` | boolean | Side-by-side comparison of all branches |

### 2. `query_combos`
Query product combination / association analysis.

| Parameter | Type | Description |
|-----------|------|-------------|
| `branch` | string | Branch filter (optional) |
| `scope` | string | Exact scope (e.g., `overall`, `branch:Conut Jnah`) |
| `min_lift` | number | Minimum lift threshold (default: 1.0) |
| `top_n` | integer | Max pairs to return (default: 10) |

### 3. `query_expansion`
Query branch expansion feasibility.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query_type` | string | Yes | `kpi`, `feasibility`, `ranking`, `recommendation`, `all_kpis` |
| `branch` | string | For kpi/feasibility | Branch name |

### 4. `query_staffing`
Query shift staffing estimation.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query_type` | string | Yes | `findings`, `gaps`, `worst_gaps`, `all_findings`, `top_gaps` |
| `branch` | string | For branch-specific | Branch name |
| `day` | string | Optional | Day of week filter |
| `top_n` | integer | Optional | Number of worst gaps |

### 5. `query_growth`
Query beverage growth strategy data.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query_type` | string | Yes | `kpi`, `potential`, `ranking`, `rules`, `recommendation`, `all_kpis` |
| `branch` | string | For branch-specific | Branch name |
| `min_lift` | number | Optional | Min lift for rules |
| `top_n` | integer | Optional | Max rules to return |

### 6. `get_overview`
Cross-feature executive overview — returns key metrics from all 5 modules in one call.
No parameters required.

### 7. `get_all_recommendations`
All strategic recommendations from every feature — expansion, growth, staffing, and combos.
No parameters required.

---

## Routes

### Chat Route (`routes/__init__.py`)

```
POST /api/chat
```

**Request:**
```json
{
  "message": "What's the demand forecast for Conut Jnah?",
  "session_id": "optional-session-id"
}
```

**Response:**
```json
{
  "answer": "Based on the demand forecast data...",
  "tool_calls": [
    {
      "tool": "query_forecast",
      "input": {"branch": "Conut Jnah"},
      "output_preview": "{\"branch\": \"Conut Jnah\", ...}"
    }
  ]
}
```

### Dashboard Routes (`routes/dashboard.py`)

Read-only GET endpoints for the frontend:

| Endpoint | Returns |
|----------|---------|
| `GET /api/dashboard/overview` | All 5 features — executive overview |
| `GET /api/dashboard/forecast` | All branch forecasts |
| `GET /api/dashboard/forecast/{branch}` | Single branch forecast |
| `GET /api/dashboard/combo` | Top 20 combo pairs |
| `GET /api/dashboard/combo/{branch}` | Combos for a branch |
| `GET /api/dashboard/expansion` | Rankings + recommendation |
| `GET /api/dashboard/expansion/{branch}` | KPIs + feasibility |
| `GET /api/dashboard/staffing` | Summary + top gaps |
| `GET /api/dashboard/staffing/{branch}` | Findings + worst gaps |
| `GET /api/dashboard/growth` | Rankings + recommendation |
| `GET /api/dashboard/growth/{branch}` | KPIs + potential + rules |

### Upload Routes (`routes/upload.py`)

| Endpoint | Description |
|----------|-------------|
| `POST /api/upload/prepare` | Archive old S3 data + clear DynamoDB tables |
| `POST /api/upload/presign` | Generate presigned S3 PUT URL |
| `POST /api/upload/trigger` | Start Step Functions pipeline |
| `POST /api/upload/status` | Check pipeline execution status |

### Health Check

```
GET /api/health
```

Returns `{"status": "ok", "local_mode": false, "model": "eu.anthropic.claude-haiku-4-5-20251001-v1:0"}`.

---

## DynamoDB Query Layer (`dynamo/`)

Each feature has a dedicated query module in `agent/dynamo/`. All modules support:

- **Cloud mode:** Queries DynamoDB tables via `boto3`
- **Local mode:** Falls back to reading local CSV files for offline development

The shared `dynamo/__init__.py` provides:
- `_get_table(name)` — Lazy DynamoDB Table resource
- `_decimal_to_float()` — Converts DynamoDB Decimal types to float
- `_read_local_csv()` — Reads CSVs with caching for local mode
- `_df_to_items()` — Converts DataFrames to JSON-safe dicts

---

## System Prompt

The system prompt (in `core/__init__.py`) instructs Claude to:

1. Always call tools to answer data questions — never make up numbers
2. Call multiple tools if the question spans multiple features
3. Present numbers clearly (2 decimal places, percentages)
4. Provide brief explanations of **why** the data says what it does
5. Back recommendations with retrieved data
6. Politely redirect off-topic questions

---

## Docker Deployment

The agent runs in a Docker container on EC2:

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY agent/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY agent/ /app/agent/
COPY analytics/ /app/analytics/
COPY conut_bakery_scaled_data/ /app/conut_bakery_scaled_data/
ENV LOCAL_MODE=false PORT=8000 HOST=0.0.0.0
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1
CMD ["python", "-m", "agent.main"]
```

### Running with Docker Locally

```bash
docker build -f agent/Dockerfile -t opsclaw-agent .

docker run -d --name opsclaw-agent \
  -p 8000:8000 \
  -e LOCAL_MODE=true \
  opsclaw-agent
```

### Dependencies

```
fastapi>=0.104
uvicorn>=0.24
pydantic>=2.0
boto3>=1.28
pandas>=2.0
numpy>=1.24
```
