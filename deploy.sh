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

# ── Build Frontend ──────────────────────────────────────────
info "Building frontend …"
pushd frontend >/dev/null
npm install --silent
npm run build
popd >/dev/null
ok "Frontend built → frontend/dist/"

# ── CDK Bootstrap (idempotent) ──────────────────────────────
info "Bootstrapping CDK …"
"$CDK_CMD" bootstrap --app "python3 infra/app.py" 2>&1 | tail -1
ok "CDK bootstrapped"

# ── Deploy / Destroy ────────────────────────────────────────
if [[ "${1:-}" == "--destroy" ]]; then
    info "Destroying all stacks …"
    "$CDK_CMD" destroy --all --force --app "python3 infra/app.py"
    ok "All stacks destroyed"
else
    info "Deploying all stacks (Pipeline → Agent → Frontend) …"
    "$CDK_CMD" deploy --all --require-approval never --app "python3 infra/app.py"
    ok "All stacks deployed 🎉"
    echo ""
    echo "Stack outputs:"
    "$CDK_CMD" list --app "python3 infra/app.py" 2>/dev/null | while read -r stack; do
        echo "  ── $stack ──"
        aws cloudformation describe-stacks --stack-name "$stack" \
            --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
            --output table 2>/dev/null || true
    done
fi
