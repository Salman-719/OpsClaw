# Infrastructure (AWS CDK)

> Three CDK stacks deploying the complete OpsClaw platform on AWS with S3, DynamoDB, Lambda, Step Functions, public EC2 origins, and CloudFront.

---

## Overview

The infrastructure is defined as **Infrastructure-as-Code** using **AWS CDK v2** (Python). It deploys three stacks with explicit dependency ordering.

```
ConutPipeline-dev  ←──  ConutAgent-dev  ←──  ConutFrontend-dev
      (no deps)         (depends on        (depends on
                         Pipeline)          Agent)
```

## File Structure

```
infra/
├── app.py               # CDK entry point — wires 3 stacks
├── cdk_stack.py         # Stack 1: Pipeline (S3, DynamoDB, Lambda, StepFunctions)
├── agent_stack.py       # Stack 2: Agent (VPC, EC2, EIP, IAM)
├── frontend_stack.py    # Stack 3: Frontend (S3, CloudFront)
├── Dockerfile           # Multi-stage Lambda Dockerfile (6 targets)
├── local_test.py        # Local testing utilities
└── handlers/            # Lambda handler functions
    ├── __init__.py
    ├── etl_handler.py
    ├── forecast_handler.py
    ├── combo_handler.py
    ├── expansion_handler.py
    ├── staffing_handler.py
    └── growth_handler.py
```

---

## Stack 1: ConutPipeline (`cdk_stack.py`)

### Resources

| Resource | Type | Name | Description |
|----------|------|------|-------------|
| **S3 Bucket** | `aws_s3.Bucket` | `conut-ops-data-dev` | Versioned, CORS-enabled, lifecycle policies |
| **DynamoDB Tables** (×5) | `aws_dynamodb.Table` | `conut-ops-{feature}-dev` | Pay-per-request, auto-scale |
| **Lambda Functions** (×6) | `aws_lambda.DockerImageFunction` | `conut-ops-{handler}-dev` | Docker images, 15min timeout, 1GB RAM |
| **Step Functions** | `aws_stepfunctions.StateMachine` | `conut-ops-pipeline-dev` | ETL → 5 parallel analytics |

### S3 Bucket Configuration

```
conut-ops-data-dev/
├── input/              # Raw uploaded CSVs land here
├── processed/          # ETL output (15 CSVs)
├── results/            # Analytics results
│   ├── forecast/
│   ├── combo/
│   ├── expansion/
│   ├── staffing/
│   └── growth/
└── archive/            # Old data archived before new upload
    └── 20260228T120000Z/
```

- **Versioning:** Enabled
- **CORS:** GET, PUT, POST from any origin (`*`)
- **Lifecycle:** Non-current versions expire after 30 days
- **Removal:** DESTROY in dev, RETAIN in prod

### DynamoDB Tables

| Table | Partition Key (pk) | Sort Key (sk) | Example |
|-------|-------------------|---------------|---------|
| `conut-ops-forecast-dev` | `branch#scenario` | `period#N` | `Conut#base` / `period#1` |
| `conut-ops-combo-dev` | Scope | `item_a#item_b` | `overall` / `Croissant#Coffee` |
| `conut-ops-expansion-dev` | Branch or `recommendation` | `kpi`, `feasibility`, `expansion` | `batroun` / `feasibility` |
| `conut-ops-staffing-dev` | Branch | `findings` or `gap#Day#Hour` | `Conut Jnah` / `gap#Monday#09` |
| `conut-ops-growth-dev` | Branch or `recommendation` | Various | `Conut Jnah` / `beverage_kpi` |

All tables use **PAY_PER_REQUEST** billing (no capacity provisioning needed).

### Lambda Functions

6 Docker Lambda functions built from a single multi-stage Dockerfile:

| Function | Dockerfile Target | Handler | Timeout | Memory |
|----------|-------------------|---------|---------|--------|
| ETL | `etl` | `infra.handlers.etl_handler.handler` | 15 min | 1024 MB |
| Forecast | `forecast` | `infra.handlers.forecast_handler.handler` | 15 min | 1024 MB |
| Combo | `combo` | `infra.handlers.combo_handler.handler` | 15 min | 1024 MB |
| Expansion | `expansion` | `infra.handlers.expansion_handler.handler` | 15 min | 1024 MB |
| Staffing | `staffing` | `infra.handlers.staffing_handler.handler` | 15 min | 1024 MB |
| Growth | `growth` | `infra.handlers.growth_handler.handler` | 15 min | 1024 MB |

The Dockerfile uses `public.ecr.aws/lambda/python:3.13` as base image.

### Step Functions State Machine

```
Start
  │
  ▼
ETL Lambda
  │
  ▼
Parallel State
  ├── Forecast Lambda
  ├── Combo Lambda
  ├── Expansion Lambda
  ├── Staffing Lambda
  └── Growth Lambda
  │
  ▼
End
```

### Exports

The Pipeline stack exports for use by other stacks:

| Export | Type | Usage |
|--------|------|-------|
| `data_bucket` | `s3.Bucket` | Agent stack (S3 access) |
| `state_machine` | `sfn.StateMachine` | Agent stack (trigger pipeline) |

---

## Stack 2: ConutAgent (`agent_stack.py`)

### Resources

| Resource | Type | Description |
|----------|------|-------------|
| **VPC** | `aws_ec2.Vpc` | Public-only; 2 AZs in `standard`, 1 AZ in `budget`; no NAT |
| **Security Group** | `aws_ec2.SecurityGroup` | Port 80 public ingress |
| **IAM Role** | `aws_iam.Role` | EC2 role with DynamoDB, Bedrock, S3, StepFunctions, SSM |
| **EC2 Instance** | `aws_ec2.Instance` | t3.micro, Amazon Linux 2023 |
| **Elastic IP** | `aws_ec2.CfnEIP` | Stable public API origin |

### IAM Permissions

| Service | Actions | Resources |
|---------|---------|-----------|
| **DynamoDB** | GetItem, Query, Scan, BatchGetItem, DeleteItem, BatchWriteItem, DescribeTable | All 5 `conut-ops-*-dev` tables |
| **Bedrock** | InvokeModel, InvokeModelWithResponseStream | All foundation models |
| **S3** | PutObject, GetObject, ListBucket, DeleteObject, CopyObject | `conut-ops-data-dev` bucket |
| **Step Functions** | StartExecution, DescribeExecution, ListExecutions | Pipeline state machine |
| **SSM** | (via AmazonSSMManagedInstanceCore) | EC2 management |

### EC2 User Data

The instance bootstraps itself:

1. Install Docker and Git
2. Clone the OpsClaw repository from GitHub
3. Build the agent Docker image
4. Run the container with environment variables:
   - `AWS_REGION=eu-west-1`
   - `LOCAL_MODE=false`
   - `S3_DATA_BUCKET=conut-ops-data-dev`
   - `STATE_MACHINE_ARN=<from pipeline stack>`
   - `BEDROCK_MODEL_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0`
   - `ORIGIN_VERIFY_HEADER_*` for CloudFront-to-origin protection

### Exports

| Export | Type | Usage |
|--------|------|-------|
| `api_origin_domain` | string | Frontend stack (CloudFront origin) |

---

## Stack 3: ConutFrontend (`frontend_stack.py`)

### Resources

| Resource | Type | Description |
|----------|------|-------------|
| **S3 Bucket** | `aws_s3.Bucket` | Static site hosting (private + OAC) |
| **CloudFront Distribution** | `aws_cloudfront.Distribution` | CDN with API proxy |
| **S3 Deployment** | `aws_s3_deployment.BucketDeployment` | Uploads `frontend/dist/` to S3 |

### CloudFront Behaviors

| Path | Origin | Cache | Methods |
|------|--------|-------|---------|
| `/*` (default) | S3 (OAC) | CACHING_OPTIMIZED | GET, HEAD |
| `/api/*` | Public EC2 origin (HTTP:80) | CACHING_DISABLED | ALL (GET, POST, PUT, DELETE, etc.) |

### SPA Error Handling

| HTTP Status | Response Status | Page | TTL |
|-------------|-----------------|------|-----|
| 404 | 200 | `/index.html` | 0s |
| 403 | 200 | `/index.html` | 0s |

This ensures React Router handles all client-side routes.

### Presigned URL Note

The agent generates presigned S3 PUT URLs using the **regional S3 endpoint** (`s3.eu-west-1.amazonaws.com`) with SigV4 signatures. This is required because the global endpoint (`s3.amazonaws.com`) returns HTTP 500 on CORS preflight (OPTIONS) requests.

---

## Networking

```
Internet
    │
    ▼ (HTTPS)
CloudFront
    │
    ├── Static assets → S3 (OAC)
    │
    └── /api/* → EC2 origin (HTTP)
                  │
                  ▼
              EC2 (Docker 80 → 8000)
                  │
                  ├── DynamoDB (5 tables)
                  ├── Bedrock (Claude)
                  ├── S3 (presigned URLs)
                  └── Step Functions (pipeline)
```

---

## CDK Commands

```bash
# Activate Python venv
source .venv/bin/activate

# Synthesize CloudFormation templates
cdk synth --app "python3 infra/app.py" --context deployment_profile=standard

# Preview changes
cdk diff --app "python3 infra/app.py" --context deployment_profile=standard

# Deploy all stacks
cdk deploy --all --require-approval never --app "python3 infra/app.py"

# Deploy specific stack
cdk deploy ConutPipeline-dev --require-approval never --app "python3 infra/app.py"

# List stacks
cdk list --app "python3 infra/app.py"

# Destroy all
cdk destroy --all --force --app "python3 infra/app.py"
```

---

## Environment Configuration

| CDK Context | Default | Description |
|-------------|---------|-------------|
| `env` | `dev` | Environment name (affects resource naming) |

Usage: `cdk deploy --context env=prod --all`

---

## Dependencies

Root `requirements.txt`:
```
pandas>=2.0
numpy>=1.26
pyarrow>=14.0
aws-cdk-lib>=2.100
constructs>=10.0
boto3>=1.28
```
