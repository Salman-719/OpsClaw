# CI/CD Pipeline

> GitHub Actions workflow with OIDC-based AWS authentication, automated testing, and 4-phase CDK deployment.

---

## Overview

The CI/CD pipeline uses **GitHub Actions** with **AWS OIDC federation** for secure, passwordless deployments. No AWS access keys are stored — authentication uses short-lived tokens via OpenID Connect.

### Pipeline Flow

```
Push to main / PR to main
         │
         ▼
┌──────────────────────────┐
│ Job 1: Unit Tests        │
│  ├── Install Python deps │
│  ├── Install Node deps   │
│  ├── Build frontend      │
│  └── Run pytest          │
└──────────┬───────────────┘
           │ (pass + push to main)
           ▼
┌──────────────────────────────────┐
│ Job 2: CDK Deploy                │
│  ├── Configure AWS (OIDC)        │
│  ├── CDK Bootstrap               │
│  ├── Phase 1: Pipeline + Agent   │
│  ├── Phase 2: Build frontend     │
│  ├── Phase 3: Deploy Frontend    │
│  └── Phase 4: Cache invalidation │
└──────────────────────────────────┘
```

---

## Workflow File

**`.github/workflows/ci-cd.yml`**

### Triggers

| Event | Branch | Action |
|-------|--------|--------|
| `push` | `main` | Run tests + deploy |
| `pull_request` | `main` | Run tests only |

### Environment Variables

| Variable | Value | Description |
|----------|-------|-------------|
| `AWS_REGION` | `eu-west-1` | AWS deployment region |
| `PYTHON_VERSION` | `3.13` | Python version for CI |
| `NODE_VERSION` | `20` | Node.js version for CI |

### Permissions

```yaml
permissions:
  id-token: write   # Required for OIDC federation
  contents: read     # Required for checkout
```

---

## Job 1: Unit Tests

Runs on **every push and PR** to `main`.

### Steps

1. **Checkout code** — `actions/checkout@v4`
2. **Set up Python 3.13** — `actions/setup-python@v5` with pip caching
3. **Install Python deps** — `requirements.txt` + `agent/requirements.txt` + pytest + httpx
4. **Set up Node.js 20** — `actions/setup-node@v4` with npm caching
5. **Install frontend deps** — `npm ci`
6. **Build frontend** — `npm run build` (validates TypeScript + Vite build)
7. **Run pytest** — `tests/test_pipeline.py` + `tests/test_agent.py` with `LOCAL_MODE=true`

### Test Environment

| Variable | Value | Purpose |
|----------|-------|---------|
| `LOCAL_MODE` | `true` | Agent reads from CSV files, not DynamoDB |

---

## Job 2: CDK Deploy

Runs **only on push to `main`** after tests pass.

### Phase 1: Deploy Pipeline + Agent

```bash
cdk deploy ConutPipeline-dev ConutAgent-dev \
  --require-approval never \
  --app "python3 infra/app.py"
```

Deploys:
- S3 data bucket
- 5 DynamoDB tables
- 6 Docker Lambda functions (built from ECR)
- Step Functions state machine
- VPC + EC2 + ALB
- IAM roles

### Phase 2: Build Frontend

```bash
cd frontend && npm run build
```

Frontend is built **after** Pipeline + Agent deploy because CloudFront needs the ALB DNS name. The frontend uses same-origin requests (no `VITE_API_URL`), so no environment variables are needed.

### Phase 3: Deploy Frontend

```bash
cdk deploy ConutFrontend-dev \
  --require-approval never \
  --app "python3 infra/app.py" \
  --outputs-file cdk-outputs.json
```

Deploys:
- S3 bucket for static assets
- CloudFront distribution with `/api/*` proxy to ALB
- Uploads `frontend/dist/` to S3

### Phase 4: CloudFront Cache Invalidation

```bash
DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name ConutFrontend-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`DistributionId`].OutputValue' \
  --output text)

aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" --paths "/*" \
  --query 'Invalidation.Status' --output text
```

Ensures users see the latest frontend immediately after deployment.

---

## AWS OIDC Setup (One-Time)

### Step 1: Create OIDC Identity Provider

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### Step 2: Create IAM Role

Create `trust-policy.json`:

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

> Replace `<ACCOUNT_ID>`, `<GITHUB_ORG>`, and `<REPO_NAME>` with your values.

```bash
aws iam create-role \
  --role-name GitHubActions-OpsClaw-Deploy \
  --assume-role-policy-document file://trust-policy.json

aws iam attach-role-policy \
  --role-name GitHubActions-OpsClaw-Deploy \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
```

> For production, replace `AdministratorAccess` with a least-privilege policy covering CloudFormation, S3, DynamoDB, Lambda, ECR, EC2, ELB, CloudFront, IAM, Step Functions, and Bedrock.

### Step 3: Add GitHub Repository Secret

1. Go to **GitHub → Repository → Settings → Secrets and variables → Actions**
2. Click **"New repository secret"**
3. Add:

| Secret Name | Value |
|-------------|-------|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/GitHubActions-OpsClaw-Deploy` |

This is the **only secret** needed. OIDC handles all authentication.

---

## GitHub Secrets Summary

| Secret | Required | Description |
|--------|----------|-------------|
| `AWS_DEPLOY_ROLE_ARN` | **Yes** | IAM role ARN that GitHub Actions assumes via OIDC |

No AWS access keys, no secret access keys — just the role ARN.

---

## Monitoring

### Check Workflow Status

1. Go to **GitHub → Repository → Actions tab**
2. Click on the latest workflow run
3. Expand each step to see logs

### Common Failures

| Failure | Cause | Fix |
|---------|-------|-----|
| OIDC auth failed | Missing/wrong `AWS_DEPLOY_ROLE_ARN` | Verify the secret value matches the IAM role ARN |
| CDK bootstrap failed | Region mismatch | Ensure `AWS_REGION` matches your setup |
| Docker build failed | ECR throttling | Retry, or check Docker build logs |
| Frontend build failed | TypeScript errors | Fix errors locally first |
| Tests failed | Missing dependencies | Check `requirements.txt` |
| Cache invalidation failed | Missing CloudFront output | Ensure Frontend stack exports `DistributionId` |

---

## Local Script Alternative

If you prefer not to use GitHub Actions, use the `deploy.sh` script:

```bash
# Deploy everything
./deploy.sh

# Tear down
./deploy.sh --destroy
```

This runs the same 4-phase deployment locally using your AWS CLI credentials.
