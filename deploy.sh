#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# deploy.sh — One-command reproducible deploy for OpsClaw
# ─────────────────────────────────────────────────────────────
# Usage:
#   ./deploy.sh              # deploy all stacks
#   ./deploy.sh --profile budget
#   ./deploy.sh --destroy    # tear down all stacks
# ─────────────────────────────────────────────────────────────
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}▸${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
fail()  { echo -e "${RED}✗${NC} $*"; exit 1; }

PROFILE="${DEPLOYMENT_PROFILE:-standard}"
ENV_NAME="${ENV_NAME:-dev}"
DESTROY=false
CDK_APP_RUNNER="$ROOT_DIR/infra/run_cdk_app.sh"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)
            PROFILE="${2:-}"
            shift 2
            ;;
        --env)
            ENV_NAME="${2:-}"
            shift 2
            ;;
        --destroy)
            DESTROY=true
            shift
            ;;
        *)
            fail "Unknown argument: $1"
            ;;
    esac
done

[[ "$PROFILE" == "standard" || "$PROFILE" == "budget" ]] \
    || fail "Invalid profile '$PROFILE' (expected standard or budget)"
[[ -n "$ENV_NAME" ]] || fail "Invalid env name"

# ── Pre-flight checks ──────────────────────────────────────
command -v node  >/dev/null || fail "node not found"
command -v npm   >/dev/null || fail "npm not found"
command -v python3 >/dev/null || fail "python3 not found"
command -v docker >/dev/null || fail "docker not found (needed for Lambda images)"

CDK_CMD="${CDK_CMD:-$(command -v cdk 2>/dev/null || echo '')}"
[[ -n "$CDK_CMD" ]] || fail "cdk CLI not found. Install: npm i -g aws-cdk"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || echo eu-west-1)}}"
PIPELINE_STACK="ConutPipeline-${ENV_NAME}"
AGENT_STACK="ConutAgent-${ENV_NAME}"
FRONTEND_STACK="ConutFrontend-${ENV_NAME}"

# ── Activate Python venv ────────────────────────────────────
if [[ -d ".venv" ]]; then
    source .venv/bin/activate
    ok "Python venv activated"
else
    info "Creating Python venv …"
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ok "Python venv created and deps installed"
fi

[[ -x "$ROOT_DIR/.venv/bin/python3" ]] || fail "Expected venv interpreter at $ROOT_DIR/.venv/bin/python3"

CDK_APP=(--app "bash $CDK_APP_RUNNER" --context "deployment_profile=${PROFILE}" --context "env=${ENV_NAME}")
if [[ -n "${ORIGIN_HEADER_NAME:-}" ]]; then
    CDK_APP+=(--context "origin_header_name=${ORIGIN_HEADER_NAME}")
fi
if [[ -n "${ORIGIN_HEADER_VALUE:-}" ]]; then
    CDK_APP+=(--context "origin_header_value=${ORIGIN_HEADER_VALUE}")
fi

# ── Install Frontend deps ───────────────────────────────────
info "Installing frontend dependencies …"
pushd frontend >/dev/null
npm install --silent
popd >/dev/null
ok "Frontend deps installed"

# ── CDK Bootstrap (idempotent) ──────────────────────────────
info "Bootstrapping CDK …"
"$CDK_CMD" bootstrap "${CDK_APP[@]}"
ok "CDK bootstrapped"

# ── Deploy / Destroy ────────────────────────────────────────
if [[ "$DESTROY" == true ]]; then
    info "Destroying all stacks …"
    "$CDK_CMD" destroy --all --force "${CDK_APP[@]}"
    ok "All stacks destroyed"
else
    # Phase 1: Deploy Pipeline + Agent (frontend needs the agent origin)
    info "Phase 1 — Deploying Pipeline + Agent (${PROFILE}) …"
    "$CDK_CMD" deploy "$PIPELINE_STACK" "$AGENT_STACK" \
        --require-approval never "${CDK_APP[@]}"
    ok "Pipeline + Agent deployed"

    # Phase 2: Build frontend (CloudFront proxies /api/* to the agent origin)
    info "Phase 2 — Building frontend …"
    pushd frontend >/dev/null
    npm run build
    popd >/dev/null
    ok "Frontend built → frontend/dist/"

    # Phase 3: Deploy Frontend stack (S3 + CloudFront)
    info "Phase 3 — Deploying Frontend …"
    "$CDK_CMD" deploy "$FRONTEND_STACK" \
        --require-approval never "${CDK_APP[@]}"
    ok "Frontend stack deployed"

    # Phase 4: Invalidate CloudFront cache
    info "Phase 4 — Invalidating CloudFront cache …"
    DIST_ID=$(aws cloudformation describe-stacks \
        --stack-name "$FRONTEND_STACK" --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`DistributionId`].OutputValue' \
        --output text)
    aws cloudfront create-invalidation \
        --distribution-id "$DIST_ID" --paths "/*" \
        --region "$REGION" \
        --query 'Invalidation.Status' --output text
    ok "All stacks deployed & cache invalidated 🎉"

    echo ""
    echo "Stack outputs:"
    "$CDK_CMD" list "${CDK_APP[@]}" 2>/dev/null | while read -r stack; do
        echo "  ── $stack ──"
        aws cloudformation describe-stacks --stack-name "$stack" \
            --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
            --output table 2>/dev/null || true
    done
fi
