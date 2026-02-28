# OpsClaw — AI-Driven Chief of Operations Agent

> **Conut AI Engineering Hackathon (AUB)** — An end-to-end cloud-native AI agent that acts as a Chief of Operations for the Conut bakery-café chain in Lebanon.
>
> **Live demo:** <https://d3gi59n7jefbjs.cloudfront.net/>

---

## Table of Contents

1. [Business Problem](#business-problem)
2. [Approach & Architecture](#approach--architecture)
3. [How to Run](#how-to-run)
4. [Key Results & Recommendations](#key-results--recommendations)
5. [Project Structure](#project-structure)
6. [Prerequisites](#prerequisites)
7. [Local Development Setup](#local-development-setup)
8. [AWS Credential Setup](#aws-credential-setup)
9. [Deployment](#deployment)
10. [CI/CD Pipeline](#cicd-pipeline)
11. [GitHub Secrets Setup](#github-secrets-setup)
12. [Usage](#usage)
13. [Testing](#testing)
14. [Module Documentation](#module-documentation)
15. [API Reference](#api-reference)
16. [Troubleshooting](#troubleshooting)

---

## Business Problem

**Conut** is a growing sweets-and-beverages business in Lebanon with four branches (Conut flagship, Conut Tyre, Conut Jnah, Main Street Coffee). The company's operational data lives in 9 report-style CSV exports covering sales, orders, time-and-attendance, staffing, and menu performance — but turning that data into actionable decisions today requires manual analysis by managers.

**The challenge:** Build an AI-powered Chief of Operations that can automatically ingest messy report CSVs, run five analytical workloads, and answer natural-language business questions — enabling Conut leadership to make data-driven decisions in real time.

The five operational questions OpsClaw addresses:

| # | Business Question | Why It Matters |
|---|------------------|----------------|
| 1 | **Which product combos sell best together?** | Enables cross-sell promotions and menu bundles that increase average order value |
| 2 | **What's the demand forecast per branch?** | Drives inventory planning, reduces waste, and prevents stock-outs |
| 3 | **Should Conut expand to a new location?** | De-risks capital expenditure with data-backed feasibility scores |
| 4 | **How many staff are needed per shift?** | Reduces labour costs from overstaffing and service degradation from understaffing |
| 5 | **How can coffee and milkshake sales grow?** | Unlocks beverage revenue potential through targeted promotions and bundle pricing |

---

## Approach & Architecture

### Approach

OpsClaw takes a **full-pipeline** approach — from raw data ingestion to AI-powered Q&A:

1. **ETL Pipeline** — 6 custom parsers auto-detect and clean the messy report-style CSVs (repeated headers, page markers, inconsistent formats), producing 15 normalised output tables.
2. **Analytics Engine** — 5 independent analytics modules run in parallel, each producing structured results with explainability metadata:
   - *Combo Optimization* — association rules (support, confidence, lift) from transaction baskets
   - *Demand Forecast* — ensemble of 4 estimators (naïve, WMA-3, linear trend, similarity transfer) with confidence bands
   - *Expansion Feasibility* — multi-KPI scoring normalised to 0–1 with weighted composite
   - *Shift Staffing* — hourly demand vs. supply gap detection per branch/day
   - *Growth Strategy* — beverage attachment rates, growth potential scores, and data-driven bundle rules
3. **AI Agent** — AWS Bedrock (Claude) with 7 tool definitions. The agent calls DynamoDB-backed query functions to answer questions with real data, not hallucinations.
4. **React Dashboard** — 7 pages (overview + one per feature + upload) with charts, KPI cards, and a persistent chat panel.
5. **Live Upload** — Users can upload new CSV data through the UI, which triggers the full pipeline via Step Functions, re-populates DynamoDB, and surfaces fresh insights immediately.

### Analytics Features

| # | Feature | Description |
|---|---------|-------------|
| 1 | **Combo Optimization** | Product-pair association rules (support, confidence, lift) |
| 2 | **Demand Forecast** | 1/2/3-month demand predictions per branch (base + optimistic) |
| 3 | **Expansion Feasibility** | KPIs and 0–1 feasibility scores for candidate branches |
| 4 | **Shift Staffing** | Hourly demand vs. supply gap analysis per branch/day |
| 5 | **Growth Strategy** | Beverage attachment rates, growth potential, bundle rules |

### Conut Branches

| Branch | Location |
|--------|----------|
| Conut | Original / flagship |
| Conut - Tyre | Southern Lebanon |
| Conut Jnah | Beirut, Jnah area |
| Main Street Coffee | Downtown main-street café |

---

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         CloudFront CDN                          │
│               (HTTPS + SPA routing + /api/* proxy)              │
├───────────────────┬─────────────────────────────────────────────┤
│   S3 (frontend)   │         ALB → EC2 (Agent)                   │
│   React Dashboard │     FastAPI + Bedrock Claude                │
└───────────────────┴──────────────┬──────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │        DynamoDB (×5)         │
                    │  forecast│combo│expansion│   │
                    │  staffing│growth              │
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              │           Step Functions                 │
              │   ETL → [Forecast│Combo│Expansion│      │
              │          Staffing│Growth] in parallel    │
              └────────────────────┬────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │    Lambda Functions (×6)      │
                    │  Docker images from ECR       │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │         S3 Data Bucket        │
                    │  input/ → processed/ → results│
                    └──────────────────────────────┘
```

### Three CDK Stacks

| Stack | Resources |
|-------|-----------|
| **ConutPipeline-dev** | S3 bucket, 5 DynamoDB tables, 6 Docker Lambda functions, Step Functions state machine |
| **ConutAgent-dev** | VPC, EC2 (t3.small), ALB, IAM roles (DynamoDB + Bedrock + S3 + StepFunctions) |
| **ConutFrontend-dev** | S3 (static hosting), CloudFront (CDN + `/api/*` proxy to ALB) |

---

## How to Run

OpsClaw supports both **local development** (no AWS needed) and **full cloud deployment**.

### Quick Start (Local — No AWS Required)

```bash
git clone https://github.com/Salman-719/OpsClaw.git
cd OpsClaw

# Python backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run ETL pipeline locally
python pipelines/run_pipeline.py --data-dir "conut_bakery_scaled_data"

# Run agent in local mode (reads CSV files, no DynamoDB)
LOCAL_MODE=true python -m agent.main     # http://localhost:8000

# Run frontend
cd frontend && npm install && npm run dev  # http://localhost:5173
```

### Full Cloud Deployment (AWS)

```bash
# Prerequisites: AWS CLI configured, CDK installed, Docker running
./deploy.sh
# Deploys 3 CDK stacks → prints CloudFront URL
```

See the [Local Development Setup](#local-development-setup) and [Deployment](#deployment) sections below for detailed instructions.

---

## Key Results & Recommendations

### Top Findings

| Feature | Key Insight | Business Impact |
|---------|-------------|-----------------|
| **Combo Optimization** | Several product pairs show lift > 2.0, meaning they are bought together far more often than chance would predict | Menu bundle promotions on high-lift pairs can increase average order value by 15–25% |
| **Demand Forecast** | Branch demand follows clear monthly seasonality with December surges flagged as anomalies; ensemble of 4 estimators delivers stable predictions with confidence bands | Proactive inventory ordering 1–3 months ahead reduces waste and stock-outs |
| **Expansion Feasibility** | Branches scored on revenue consistency, growth trajectory, and operational efficiency yield a clear ranking; data-starved branches (< 4 months) use similarity transfer from comparable locations | Investment decisions can be backed by composite 0–1 feasibility scores instead of gut feeling |
| **Shift Staffing** | Multiple branches show systematic understaffing during lunch (11:00–14:00) and weekend peaks, with demand-supply gaps up to 3–4 staff | Realigning rosters to the demand curve can reduce overtime costs and improve customer wait times |
| **Growth Strategy** | Beverage attachment rates vary significantly by branch; some locations have < 30% attachment on high-margin drinks | Targeted upsell training and bundle pricing at underperforming branches can unlock 10–20% beverage revenue growth |

### Recommendations

1. **Launch combo bundles** — Start with the top-5 product pairs by lift score as promotional bundles. Monitor basket size impact weekly.
2. **Adopt rolling forecasts** — Use the 1-month base-case forecast for purchasing; use the 3-month extension for supplier negotiations.
3. **Delay expansion until data matures** — Branches with < 6 months of data should wait; use the similarity-transfer forecast for early estimates.
4. **Rebalance shift rosters** — Address the top-10 understaffed time-slots first. Even small shifts (1–2 staff) at peak times materially improve throughput.
5. **Beverage upsell program** — Target the branch with the lowest attachment rate for a 4-week upsell pilot. Measure before/after attachment rate and revenue per ticket.
6. **Automate the pipeline** — With OpsClaw, new CSV uploads trigger the full analytics pipeline automatically. Conut should schedule weekly data exports and uploads to keep insights current.

### Technical Results

- **ETL Pipeline:** 6 parsers handle 9 messy report-style CSVs → 15 clean normalised tables, 100% automated
- **Analytics:** 5 features run in parallel via Step Functions (< 2 min end-to-end)
- **Agent:** Claude answers business questions using 7 tools backed by DynamoDB — zero hallucination on data queries
- **Test Suite:** 29 tests across ETL, agent API, and CDK infrastructure
- **CI/CD:** GitHub Actions with OIDC → fully automated deploy on push to `main`

---

## Project Structure

```
OpsClaw/
├── agent/                    # FastAPI agent service
│   ├── main.py              # App entry point
│   ├── config.py            # Environment-based configuration
│   ├── Dockerfile           # Agent Docker image
│   ├── requirements.txt     # Agent Python dependencies
│   ├── core/
│   │   ├── __init__.py      # System prompt for Claude
│   │   └── agent.py         # Bedrock Converse API + tool-calling loop
│   ├── dynamo/              # DynamoDB query layer (5 modules)
│   │   ├── __init__.py      # Shared helpers + local CSV fallback
│   │   ├── combo.py         # Feature 1 queries
│   │   ├── forecast.py      # Feature 2 queries
│   │   ├── expansion.py     # Feature 3 queries
│   │   ├── staffing.py      # Feature 4 queries
│   │   └── growth.py        # Feature 5 queries
│   ├── models/
│   │   └── __init__.py      # Pydantic request/response schemas
│   ├── routes/
│   │   ├── __init__.py      # POST /api/chat (chat endpoint)
│   │   ├── dashboard.py     # GET /api/dashboard/* (data endpoints)
│   │   └── upload.py        # POST /api/upload/* (upload + pipeline)
│   └── tools/
│       ├── __init__.py      # Bedrock tool specs (7 tools)
│       └── executor.py      # Tool name → function dispatcher
│
├── analytics/                # Analytics feature modules
│   ├── combo/               # Feature 1: Combo Optimization
│   ├── forecast/            # Feature 2: Demand Forecasting
│   ├── expansion/           # Feature 3: Expansion Feasibility
│   ├── staffing/            # Feature 4: Shift Staffing
│   └── growth/              # Feature 5: Growth Strategy
│
├── pipelines/                # ETL data pipeline
│   ├── run_pipeline.py      # Orchestrator (auto-detect + parse + features)
│   ├── parsers/             # 6 CSV parsers + dimensions + features
│   └── output/              # Pipeline output CSVs (15 files)
│
├── infra/                    # AWS CDK infrastructure
│   ├── app.py               # CDK entry point (3 stacks)
│   ├── cdk_stack.py         # Pipeline stack (S3+DynamoDB+Lambda+StepFunctions)
│   ├── agent_stack.py       # Agent stack (EC2+ALB+IAM)
│   ├── frontend_stack.py    # Frontend stack (S3+CloudFront)
│   ├── Dockerfile           # Multi-stage Lambda Dockerfile (6 targets)
│   └── handlers/            # Lambda handler functions
│       ├── etl_handler.py
│       ├── forecast_handler.py
│       ├── combo_handler.py
│       ├── expansion_handler.py
│       ├── staffing_handler.py
│       └── growth_handler.py
│
├── frontend/                 # React dashboard
│   ├── package.json
│   └── src/
│       ├── App.tsx          # Router + layout
│       ├── api.ts           # API client (same-origin via CloudFront)
│       ├── components/      # Sidebar, ChatPanel, Card, KpiCard, Spinner
│       └── pages/           # Dashboard, Forecast, Combo, Expansion, Staffing, Growth, Upload
│
├── tests/                    # Unit + integration tests
│   ├── test_pipeline.py     # ETL pipeline tests
│   ├── test_agent.py        # FastAPI agent tests
│   └── test_infra.py        # CDK infrastructure tests
│
├── docs/                     # Module documentation
├── .github/workflows/        # CI/CD
│   └── ci-cd.yml            # GitHub Actions (test + deploy)
├── deploy.sh                # One-command deploy script
├── get_url.sh               # Helper: print CloudFront URL
├── requirements.txt          # Root Python dependencies
└── cdk.json                  # CDK configuration
```

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| **Python** | 3.13+ | Backend, analytics, CDK |
| **Node.js** | 20+ | Frontend build, CDK CLI |
| **Docker** | Latest | Lambda images, agent container |
| **AWS CLI** | v2 | Cloud deployment |
| **AWS CDK** | 2.100+ | Infrastructure as Code |
| **Git** | Latest | Version control |

### Install CDK CLI

```bash
npm install -g aws-cdk
```

---

## Local Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Salman-719/OpsClaw.git
cd OpsClaw
```

### 2. Set Up Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
pip install -r requirements.txt
```

### 3. Run the ETL Pipeline Locally

```bash
python pipelines/run_pipeline.py --data-dir "conut_bakery_scaled_data"
```

This processes sample CSV files and outputs 15 clean CSVs to `pipelines/output/`.

### 4. Run the Agent Locally

```bash
# LOCAL_MODE reads from CSV files instead of DynamoDB
export LOCAL_MODE=true
python -m agent.main
```

The agent starts at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

### 5. Run the Frontend Locally

```bash
cd frontend
npm install
npm run dev
```

Frontend starts at `http://localhost:5173`. It connects to the agent at the same origin (configure `VITE_API_URL=http://localhost:8000` for local dev if needed).

---

## AWS Credential Setup

### Option A: AWS CLI Profile (Local Development)

```bash
# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip && sudo ./aws/install

# Configure credentials
aws configure
# Enter:
#   AWS Access Key ID:     <your-key>
#   AWS Secret Access Key: <your-secret>
#   Default region:        eu-west-1
#   Default output format: json

# Verify
aws sts get-caller-identity
```

### Option B: Environment Variables

```bash
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=wJal...
export AWS_DEFAULT_REGION=eu-west-1
```

### Option C: IAM Role (EC2/CI)

The EC2 instance and CI/CD pipeline use IAM roles automatically. No manual credentials needed.

### Required IAM Permissions

The deploying user/role needs:

- **CloudFormation** — full access (CDK uses this)
- **S3** — create buckets, upload objects
- **DynamoDB** — create tables, read/write items
- **Lambda** — create/update functions
- **ECR** — push Docker images
- **EC2** — create instances, VPCs, security groups
- **ELB** — create load balancers
- **CloudFront** — create distributions, invalidations
- **IAM** — create roles and policies
- **Step Functions** — create state machines
- **Bedrock** — invoke models (Claude)
- **SSM** — manage EC2 instances

> **Tip:** For hackathon/dev, `AdministratorAccess` policy works. For production, use least-privilege.

---

## Deployment

### One-Command Deploy

```bash
./deploy.sh
```

This runs a **4-phase deployment**:

1. **Phase 1** — Deploy `ConutPipeline-dev` + `ConutAgent-dev` (S3, DynamoDB, Lambda, EC2, ALB)
2. **Phase 2** — Build the React frontend (`npm run build`)
3. **Phase 3** — Deploy `ConutFrontend-dev` (S3 + CloudFront, uploads built files)
4. **Phase 4** — Invalidate CloudFront cache

After deployment, the script prints all stack outputs including the **CloudFront URL**.

### Get the Frontend URL

```bash
./get_url.sh
# Output: https://d3gi59n7jefbjs.cloudfront.net
```

### Deploy Individual Stacks

```bash
# Python venv must be active
source .venv/bin/activate

# Deploy only the pipeline
cdk deploy ConutPipeline-dev --require-approval never --app "python3 infra/app.py"

# Deploy only the agent
cdk deploy ConutAgent-dev --require-approval never --app "python3 infra/app.py"

# Deploy only the frontend
cd frontend && npm run build && cd ..
cdk deploy ConutFrontend-dev --require-approval never --app "python3 infra/app.py"
```

### Tear Down

```bash
./deploy.sh --destroy
```

---

## CI/CD Pipeline

The project uses **GitHub Actions** with AWS OIDC federation for secure, passwordless deployments.

### Workflow: `.github/workflows/ci-cd.yml`

| Trigger | Job | Actions |
|---------|-----|---------|
| Push/PR to `main` | **test** | Install deps → Build frontend → Run pytest |
| Push to `main` | **deploy** | Authenticate via OIDC → CDK bootstrap → 4-phase deploy → Invalidate cache |

### Pipeline Flow

```
Push to main
    │
    ├─► Unit Tests (Python + Frontend build)
    │       ↓ (pass)
    └─► CDK Deploy
            ├─ Phase 1: Pipeline + Agent stacks
            ├─ Phase 2: Build frontend
            ├─ Phase 3: Frontend stack
            └─ Phase 4: Cache invalidation
```

---

## GitHub Secrets Setup

### Step 1: Create OIDC Identity Provider in AWS

```bash
# One-time setup — creates the GitHub OIDC provider in your AWS account
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### Step 2: Create IAM Role for GitHub Actions

Create a file `trust-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:<GITHUB_ORG>/<REPO_NAME>:*"
        }
      }
    }
  ]
}
```

Replace `<ACCOUNT_ID>` with your AWS account ID and `<GITHUB_ORG>/<REPO_NAME>` with your repo (e.g., `Salman-719/OpsClaw`).

```bash
aws iam create-role \
  --role-name GitHubActions-OpsClaw-Deploy \
  --assume-role-policy-document file://trust-policy.json

# Attach AdministratorAccess (or a custom least-privilege policy)
aws iam attach-role-policy \
  --role-name GitHubActions-OpsClaw-Deploy \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
```

### Step 3: Add Secret to GitHub Repository

1. Go to **GitHub → Repository → Settings → Secrets and variables → Actions**
2. Click **"New repository secret"**
3. Add:

| Secret Name | Value |
|-------------|-------|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/GitHubActions-OpsClaw-Deploy` |

That's the **only secret needed**. OIDC handles authentication — no access keys required.

### Step 4: Verify

Push a commit to `main` and check the **Actions** tab. The workflow should:
1. Run unit tests (green checkmark)
2. Deploy all 3 CDK stacks
3. Invalidate CloudFront cache
4. Print stack outputs

---

## Usage

### Chat with the Agent

Visit the CloudFront URL and use the chat panel:

```
"What's the demand forecast for Conut Jnah?"
"Which product combos have the highest lift?"
"Should we expand to Batroun?"
"Show me staffing gaps for Main Street Coffee on Saturday"
"What's the growth potential for beverages?"
"Give me an executive overview"
```

### Upload New Data

1. Navigate to the **Upload** page
2. Click **"Prepare"** — archives old data + clears DynamoDB tables
3. Select your CSV files (any name — detection is content-based)
4. Click **"Upload"** — files are uploaded to S3 via presigned URLs
5. Click **"Run Pipeline"** — triggers Step Functions (ETL → 5 analytics)
6. Monitor the pipeline status until completion
7. Chat with the agent about the new data

### Dashboard Pages

| Page | Route | Description |
|------|-------|-------------|
| Dashboard | `/` | Executive overview — all 5 features |
| Forecast | `/forecast` | Branch-by-branch demand predictions |
| Combos | `/combo` | Top product pairs by lift/confidence |
| Expansion | `/expansion` | Branch feasibility scores + rankings |
| Staffing | `/staffing` | Hourly gaps + understaffing alerts |
| Growth | `/growth` | Beverage potential + bundle rules |
| Upload | `/upload` | Upload data + trigger pipeline |

---

## Testing

```bash
# Activate venv
source .venv/bin/activate

# Install test dependencies
pip install pytest httpx

# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_pipeline.py -v
python -m pytest tests/test_agent.py -v
python -m pytest tests/test_infra.py -v
```

### Test Summary (29 tests)

| File | Tests | Covers |
|------|-------|--------|
| `test_pipeline.py` | 7 | ETL report detection, parser registry, integration run |
| `test_agent.py` | 15 | Health, chat, dashboard (6 features), upload (4 blocked), models (4) |
| `test_infra.py` | 7 | CDK stack synthesis — resource counts, properties, exports |

---

## Module Documentation

Detailed documentation for each module is in the `docs/` directory:

| Document | Description |
|----------|-------------|
| [docs/ETL_PIPELINE.md](docs/ETL_PIPELINE.md) | ETL pipeline — parsers, detection, output schema |
| [docs/ANALYTICS.md](docs/ANALYTICS.md) | All 5 analytics features — methodology + outputs |
| [docs/AGENT.md](docs/AGENT.md) | AI agent — Bedrock integration, tools, routes |
| [docs/FRONTEND.md](docs/FRONTEND.md) | React dashboard — pages, components, API client |
| [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) | CDK stacks, Lambda, DynamoDB schema, networking |
| [docs/CI_CD.md](docs/CI_CD.md) | GitHub Actions, OIDC, deployment workflow |
| [docs/TESTING.md](docs/TESTING.md) | Test suite, running tests, coverage |

---

## API Reference

### Chat

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` | Send a message to the AI agent |
| `GET` | `/api/health` | Health check |

### Dashboard

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/dashboard/overview` | Cross-feature executive overview |
| `GET` | `/api/dashboard/forecast` | All branch forecasts |
| `GET` | `/api/dashboard/forecast/{branch}` | Forecast for a specific branch |
| `GET` | `/api/dashboard/combo` | Top 20 combo pairs |
| `GET` | `/api/dashboard/combo/{branch}` | Combos for a specific branch |
| `GET` | `/api/dashboard/expansion` | Expansion rankings + recommendation |
| `GET` | `/api/dashboard/expansion/{branch}` | KPIs + feasibility for a branch |
| `GET` | `/api/dashboard/staffing` | Staffing summary + top gaps |
| `GET` | `/api/dashboard/staffing/{branch}` | Findings + worst gaps for a branch |
| `GET` | `/api/dashboard/growth` | Growth rankings + recommendation |
| `GET` | `/api/dashboard/growth/{branch}` | KPIs + potential + rules for a branch |

### Upload

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload/prepare` | Archive old data + clear DynamoDB |
| `POST` | `/api/upload/presign` | Get presigned S3 upload URL |
| `POST` | `/api/upload/trigger` | Start Step Functions pipeline |
| `POST` | `/api/upload/status` | Check pipeline execution status |

---

## Troubleshooting

### Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `cdk deploy` fails with JSII error | `/tmp` full | `rm -rf /tmp/jsii*` |
| Frontend shows "Failed to fetch" | CloudFront cache stale | `aws cloudfront create-invalidation --distribution-id <ID> --paths "/*"` |
| Upload CORS error | S3 global endpoint | Agent uses regional endpoint (`s3.eu-west-1.amazonaws.com`) — ensure latest code is deployed |
| Agent returns empty data | DynamoDB tables empty | Upload data + run pipeline, or check `LOCAL_MODE` |
| CDK deploy hangs | Zombie CDK process | `pkill -9 -f cdk && rm -rf cdk.out` |

### Useful Commands

```bash
# Check agent health
curl https://<cloudfront-url>/api/health

# Check EC2 agent directly
curl http://<alb-dns>/api/health

# View EC2 logs via SSM
aws ssm send-command \
  --instance-ids <instance-id> \
  --document-name "AWS-RunShellScript" \
  --parameters commands='["docker logs opsclaw-agent --tail 50"]'

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id <dist-id> --paths "/*"

# Check pipeline execution
aws stepfunctions list-executions \
  --state-machine-arn <sfn-arn> --max-results 5
```

---

## License

Built for the Conut AI Engineering Hackathon at AUB.
