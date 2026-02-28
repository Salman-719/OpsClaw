#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# deploy.sh — One-command reproducible deploy for OpsClaw
# ─────────────────────────────────────────────────────────────
# Usage:
#   ./deploy.sh              # deploy all stacks
#   ./deploy.sh --destroy    # tear down all stacks
# ─────────────────────────────────────────────────────────────
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}▸${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
fail()  { echo -e "${RED}✗${NC} $*"; exit 1; }

# ── Pre-flight checks ──────────────────────────────────────
command -v node  >/dev/null || fail "node not found"
command -v npm   >/dev/null || fail "npm not found"
command -v python3 >/dev/null || fail "python3 not found"
command -v docker >/dev/null || fail "docker not found (needed for Lambda images)"

CDK_CMD="${CDK_CMD:-$(command -v cdk 2>/dev/null || echo '')}"
[[ -n "$CDK_CMD" ]] || fail "cdk CLI not found. Install: npm i -g aws-cdk"

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

# ── Install Frontend deps ───────────────────────────────────
info "Installing frontend dependencies …"
pushd frontend >/dev/null
npm install --silent
popd >/dev/null
ok "Frontend deps installed"

# ── CDK Bootstrap (idempotent) ──────────────────────────────
info "Bootstrapping CDK …"
"$CDK_CMD" bootstrap --app "python3 infra/app.py"
ok "CDK bootstrapped"

# ── Deploy / Destroy ────────────────────────────────────────
if [[ "${1:-}" == "--destroy" ]]; then
    info "Destroying all stacks …"
    "$CDK_CMD" destroy --all --force --app "python3 infra/app.py"
    ok "All stacks destroyed"
else
    # Phase 1: Deploy Pipeline + Agent (need ALB URL before building frontend)
    info "Phase 1 — Deploying Pipeline + Agent …"
    "$CDK_CMD" deploy ConutPipeline-dev ConutAgent-dev \
        --require-approval never --app "python3 infra/app.py"
    ok "Pipeline + Agent deployed"

    # Phase 2: Build frontend (CloudFront proxies /api/* to ALB, no VITE_API_URL needed)
    info "Phase 2 — Building frontend …"
    pushd frontend >/dev/null
    npm run build
    popd >/dev/null
    ok "Frontend built → frontend/dist/"

    # Phase 3: Deploy Frontend stack (S3 + CloudFront)
    info "Phase 3 — Deploying Frontend …"
    "$CDK_CMD" deploy ConutFrontend-dev \
        --require-approval never --app "python3 infra/app.py"
    ok "Frontend stack deployed"

    # Phase 4: Invalidate CloudFront cache
    info "Phase 4 — Invalidating CloudFront cache …"
    DIST_ID=$(aws cloudformation describe-stacks \
        --stack-name ConutFrontend-dev --region "${AWS_REGION:-eu-west-1}" \
        --query 'Stacks[0].Outputs[?OutputKey==`DistributionId`].OutputValue' \
        --output text)
    aws cloudfront create-invalidation \
        --distribution-id "$DIST_ID" --paths "/*" \
        --region "${AWS_REGION:-eu-west-1}" \
        --query 'Invalidation.Status' --output text
    ok "All stacks deployed & cache invalidated 🎉"

    echo ""
    echo "Stack outputs:"
    "$CDK_CMD" list --app "python3 infra/app.py" 2>/dev/null | while read -r stack; do
        echo "  ── $stack ──"
        aws cloudformation describe-stacks --stack-name "$stack" \
            --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
            --output table 2>/dev/null || true
    done
fi
