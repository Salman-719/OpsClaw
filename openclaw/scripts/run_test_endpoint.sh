#!/usr/bin/env bash
# Start the test endpoint (Bash)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Installing test endpoint dependencies..."
pip install -r "$SCRIPT_DIR/test_endpoint/requirements.txt" -q

echo "Starting test endpoint on http://0.0.0.0:8000"
uvicorn openclaw.test_endpoint.test_endpoint:app --host 0.0.0.0 --port 8000
