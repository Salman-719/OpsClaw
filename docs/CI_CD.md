# CI/CD — GitHub Actions

## Overview

Every push to `main` triggers a two-stage pipeline:

```
Push → [Unit Tests] → (all pass?) → [CDK Deploy] → AWS
```

Pull requests run tests only — no deploy.

---

## Pipeline Stages

### Stage 1 — Unit Tests

| What | Detail |
|------|--------|
| Trigger | Every push & PR to `main` |
| Runner | `ubuntu-latest` |
| Python | 3.13 |
| Node | 20 |
| Tests | 29 tests across 2 suites |

**Test suites:**

- `tests/test_pipeline.py` — ETL parsers, report type detection, full pipeline integration
- `tests/test_agent.py` — FastAPI routes (health, chat, dashboard, upload), Pydantic models, config

**Run locally:**

```bash
source .venv/bin/activate
LOCAL_MODE=true python -m pytest tests/test_pipeline.py tests/test_agent.py -v
```

### Stage 2 — CDK Deploy

| What | Detail |
|------|--------|
| Trigger | Only on push to `main`, after tests pass |
| Auth | AWS OIDC (no long-lived keys) |
| Stacks | `ConutPipeline-dev` → `ConutAgent-dev` → `ConutFrontend-dev` |

Deploys all three stacks in dependency order:
1. **Pipeline** — S3, DynamoDB (5 tables), Lambda (6 functions), Step Functions
2. **Agent** — VPC, EC2 (t3.small), ALB, IAM roles
3. **Frontend** — S3 + CloudFront CDN

---

## Setup Instructions

### 1. Create OIDC Identity Provider (one-time per AWS account)

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 2. Create the Deploy Role

```bash
aws iam create-role \
  --role-name github-opsclaw-deploy \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
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
          "token.actions.githubusercontent.com:sub": "repo:Salman-719/OpsClaw:*"
        }
      }
    }]
  }'
```

> Replace `<ACCOUNT_ID>` with your AWS account ID (e.g. `692461731658`).

### 3. Attach Permissions

```bash
aws iam attach-role-policy \
  --role-name github-opsclaw-deploy \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
```

> For production, scope this down to CloudFormation, S3, EC2, Lambda, DynamoDB, etc.

### 4. Add GitHub Secret

1. Go to **GitHub → Repo → Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `AWS_DEPLOY_ROLE_ARN`
4. Value: `arn:aws:iam::<ACCOUNT_ID>:role/github-opsclaw-deploy`

---

## Workflow File

Located at `.github/workflows/ci-cd.yml`.

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| OIDC auth (no access keys) | More secure — short-lived tokens, no stored credentials |
| Tests skip CDK synth | CDK synth builds Docker images (~5 min); pipeline + agent tests run in ~1s |
| `--require-approval never` | Automated deploy — no manual review gates |
| Frontend built in both jobs | Test job validates build; deploy job needs `dist/` for CDK |

### Environment Variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `AWS_REGION` | Workflow env | `eu-west-1` |
| `LOCAL_MODE` | Test step | Forces agent to use CSV fallback |
| `AWS_DEPLOY_ROLE_ARN` | GitHub secret | IAM role for OIDC auth |

---

## Troubleshooting

**Tests fail locally but pass in CI:**
- Ensure `LOCAL_MODE=true` is set
- Run from project root: `cd /path/to/Hackathon && python -m pytest ...`

**Deploy fails with "Bootstrap required":**
- The workflow runs `cdk bootstrap` automatically
- If it persists, run manually: `cdk bootstrap aws://<ACCOUNT_ID>/eu-west-1`

**Deploy fails with "Free Tier" error:**
- EC2 instance is `t3.small` — ensure your account allows it
- If restricted, change `instance_type` in `infra/agent_stack.py` to `t2.micro`

**OIDC fails with "Not authorized to perform sts:AssumeRoleWithWebIdentity":**
- Verify the trust policy `sub` condition matches your repo name
- Check the OIDC provider thumbprint is correct
