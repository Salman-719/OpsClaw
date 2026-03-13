# Conut Chief of Operations Agent — Current Architecture Plan

## Summary

The current implementation is a three-stack AWS deployment:

1. `ConutPipeline-<env>` — S3 data bucket, 5 DynamoDB tables, 6 Lambda containers, Step Functions state machine
2. `ConutAgent-<env>` — public-only VPC, one EC2 `t3.micro`, IAM role, Elastic IP, Dockerized FastAPI agent
3. `ConutFrontend-<env>` — private S3 frontend bucket, CloudFront distribution, `/api/*` proxy to the agent origin

The cost-optimization work is already applied:

- no NAT gateway
- no Application Load Balancer
- one public EC2 origin behind CloudFront
- `t3.micro` for both deployment profiles

## Deployed Topology

```text
Users
  |
  v
CloudFront
  |-- /*      -> S3 frontend bucket
  `-- /api/*  -> EC2 public origin (HTTP:80)
                    |
                    v
              FastAPI agent container
                    |
        +-----------+-----------+-----------+
        |                       |           |
        v                       v           v
    DynamoDB                 Step Functions  Bedrock
     (5 tables)               + Lambdas      Claude Haiku 4.5
        ^
        |
        v
   S3 data bucket
```

## Deployment Profiles

Both profiles use the same stack names and same application behavior. The difference is only infrastructure footprint.

### `standard`

- 2 public subnets across 2 AZs
- 1 EC2 `t3.micro`
- 30 GB gp3 root volume
- no NAT
- no ALB

### `budget`

- 1 public subnet in 1 AZ
- 1 EC2 `t3.micro`
- 20 GB gp3 root volume
- no NAT
- no ALB

## Agent Runtime

The agent stack bootstraps itself with EC2 user data:

1. install Docker + Git
2. clone the repo on the instance
3. build `agent/Dockerfile`
4. run the container on host port `80` mapped to container port `8000`

The container receives:

- `AWS_REGION`
- `ENV_NAME`
- `S3_DATA_BUCKET`
- `STATE_MACHINE_ARN`
- `BEDROCK_MODEL_ID=anthropic.claude-haiku-4-5-20251001-v1:0`
- `ORIGIN_VERIFY_HEADER_NAME`
- `ORIGIN_VERIFY_HEADER_VALUE`

## Frontend / Origin Protection

CloudFront is the public entry point for both static assets and API traffic.

- static assets are served from S3 with Origin Access Control
- `/api/*` is forwarded to the EC2 origin on HTTP/80
- CloudFront injects a shared secret header
- FastAPI validates that header in cloud mode

This replaces the old ALB-based origin shielding.

## Data Flow

### Upload flow

1. frontend calls `/api/upload/prepare`
2. agent archives previous S3 data and clears DynamoDB
3. frontend uploads CSV files with presigned S3 URLs
4. frontend calls `/api/upload/trigger`
5. Step Functions runs ETL then the 5 analytics Lambdas
6. frontend polls `/api/upload/status`
7. dashboard and chat read refreshed results from DynamoDB

### Read flow

1. frontend calls dashboard or chat endpoints through CloudFront
2. agent reads DynamoDB data and, for chat, calls Bedrock
3. results are returned on the same CloudFront origin

## Deployment Commands

Recommended path:

```bash
./deploy.sh --profile standard --env dev
./deploy.sh --profile budget --env dev
```

Helper:

```bash
ENV_NAME=dev ./get_url.sh
```

Direct CDK path:

```bash
cdk deploy --app "bash infra/run_cdk_app.sh" \
  --context env=dev \
  --context deployment_profile=budget \
  --all
```

## Important Notes

- The pipeline bucket name is intentionally stable: `conut-ops-data-<env>`
- Stack order remains `Pipeline -> Agent -> Frontend`
- CloudFront cache invalidation happens during frontend deployment and again in `deploy.sh`
- The current migration keeps a temporary legacy agent export so older frontend imports do not block stack updates
