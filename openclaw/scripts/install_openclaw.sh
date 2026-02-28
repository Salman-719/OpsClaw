#!/usr/bin/env bash
# Install OpenClaw on macOS / Linux / WSL
set -euo pipefail

echo "=== Installing OpenClaw ==="

if ! command -v node &>/dev/null; then
    echo "ERROR: Node.js is required. Install from https://nodejs.org/"
    exit 1
fi

echo "Node.js $(node --version) detected"

npm install -g openclaw
npm install -g clawhub

echo "=== Verifying installation ==="
openclaw --version

echo ""
echo "✅ OpenClaw installed. Next steps:"
echo "   1. Run: openclaw doctor --fix"
echo "   2. Follow docs/OPENCLAW_GUIDE.md for full setup"
