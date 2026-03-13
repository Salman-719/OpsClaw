# OpsClaw Agent — Deployment Guide

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        CDK Deploy --all                          │
├───────────────┬───────────────────┬──────────────────────────────┤
│  Pipeline     │  Agent Service    │  Frontend                    │
│  Stack        │  Stack            │  Stack                       │
│               │                   │                              │
│  S3 Bucket    │  VPC + Subnets    │  S3 Bucket (static)          │
│  5 DynamoDB   │  EC2 (t3.micro)   │  CloudFront CDN              │
│  6 Lambdas    │  Elastic IP       │  React Dashboard             │
│  Step Funcs   │  IAM Roles        │  Chatbot Interface           │
│               │  (Bedrock + Dyn.) │                              │
└───────────────┴───────────────────┴──────────────────────────────┘
         ▲               ▲                      │
         │               │                      │
         │   DynamoDB    │    HTTP /api/*        │
         │   read        │    ◄─────────────────┘
         │               │
    CSV upload      Bedrock Claude Haiku 4.5
    triggers         tool-calling
    pipeline
```

## Prerequisites

1. **AWS CLI** configured with credentials (`aws configure`)
2. **CDK CLI** installed (`npm install -g aws-cdk`)
3. **Python 3.13+** with venv
4. **Node.js 18+** (for CDK and frontend build)
5. **Docker** running locally (CDK builds Lambda images)
6. **AWS Bedrock** — Claude Haiku 4.5 model access enabled in your region

## Quick Deploy (One Command)

```bash
# From project root
source .venv/bin/activate

# Build the frontend first
cd frontend && npm install && npm run build && cd ..

# Deploy everything
cdk deploy --all --require-approval never --context deployment_profile=standard
```

## Step-by-Step Deploy

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Build the frontend

```bash
cd frontend
npm install
npm run build    # produces frontend/dist/
cd ..
```

### 3. Deploy individual stacks (or all at once)

```bash
# Deploy pipeline first (S3 + DynamoDB + Lambdas + Step Functions)
cdk deploy ConutPipeline-dev

# Deploy agent service (public EC2 origin)
cdk deploy ConutAgent-dev --context deployment_profile=standard

# Deploy frontend (S3 + CloudFront)
cdk deploy ConutFrontend-dev

# Or deploy everything:
cdk deploy --all
```

### 4. Verify deployment

After deploy, CDK prints outputs:

| Output              | Description                          |
|---------------------|--------------------------------------|
| AgentOriginUrl      | Agent API origin URL                 |
| FrontendURL         | Dashboard URL (CloudFront HTTPS)     |
| DataBucketName      | S3 bucket for CSV uploads            |
| StateMachineArn     | Step Functions pipeline ARN          |

Test the agent:
```bash
curl https://<FrontendURL>/api/health
curl -X POST https://<FrontendURL>/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Give me an overview"}'
```

## Stack Details

### ConutPipeline Stack
- **S3 Bucket**: Receives raw CSV data. Upload triggers the ETL pipeline.
- **DynamoDB Tables** (5): forecast, combo, expansion, staffing, growth
- **Lambda Functions** (6): ETL, Forecast, Combo, Expansion, Staffing, Growth
- **Step Functions**: ETL → 5 analytics Lambdas in parallel

### ConutAgent Stack
- **VPC**: public-only; 2 AZs in `standard`, 1 AZ in `budget`; no NAT gateway
- **EC2 Instance**: t3.micro, Amazon Linux 2023, runs agent Docker container
- **Elastic IP**: stable public origin for CloudFront `/api/*`
- **IAM Role**: DynamoDB read (5 tables) + Bedrock InvokeModel
- **User Data**: Auto-clones repo, builds Docker image, starts container

### ConutFrontend Stack
- **S3 Bucket**: Hosts built React app (frontend/dist/)
- **CloudFront**: CDN with HTTPS, SPA fallback (index.html for 404s)
- **OAI**: S3 access via CloudFront Origin Access Identity

## Environment Variables (Agent)

| Variable               | Default                               | Description              |
|------------------------|---------------------------------------|--------------------------|
| AWS_REGION             | eu-west-1                             | AWS region               |
| ENV_NAME               | dev                                   | Environment suffix       |
| LOCAL_MODE             | false                                 | Use local CSVs (testing) |
| BEDROCK_MODEL_ID       | anthropic.claude-haiku-4-5-20251001-v1:0 | Bedrock model         |
| BEDROCK_MAX_TOKENS     | 4096                                  | Max response tokens      |
| BEDROCK_TEMPERATURE    | 0.1                                   | LLM temperature          |
| PORT                   | 8000                                  | API port                 |
| ORIGIN_VERIFY_HEADER_* | set by CDK deploy                     | CloudFront origin guard  |

## API Endpoints

| Method | Path                            | Description                     |
|--------|----------------------------------|---------------------------------|
| GET    | /api/health                      | Health check                    |
| POST   | /api/chat                        | Chatbot Q&A                     |
| GET    | /api/dashboard/overview          | Executive overview              |
| GET    | /api/dashboard/forecast          | All forecasts                   |
| GET    | /api/dashboard/forecast/{branch} | Branch forecast                 |
| GET    | /api/dashboard/combo             | Top combos                      |
| GET    | /api/dashboard/combo/{branch}    | Branch combos                   |
| GET    | /api/dashboard/expansion         | Expansion ranking               |
| GET    | /api/dashboard/expansion/{branch}| Branch expansion                |
| GET    | /api/dashboard/staffing          | Staffing summary                |
| GET    | /api/dashboard/staffing/{branch} | Branch staffing                 |
| GET    | /api/dashboard/growth            | Growth ranking                  |
| GET    | /api/dashboard/growth/{branch}   | Branch growth                   |

## Local Development

```bash
# Run agent locally (no AWS needed)
LOCAL_MODE=true python -m agent.main

# Run frontend dev server
cd frontend && npm run dev
```

## Teardown

```bash
cdk destroy --all
```
