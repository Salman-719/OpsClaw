#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python3"

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Missing venv interpreter at $VENV_PYTHON" >&2
    exit 1
fi

mkdir -p "$ROOT_DIR/.cache"
export PYTHONNOUSERSITE=1
export XDG_CACHE_HOME="$ROOT_DIR/.cache"

exec "$VENV_PYTHON" "$ROOT_DIR/infra/app.py" "$@"
