#!/usr/bin/env bash
# Deploy reference config to ~/.openclaw/ (Bash)
# NOTE: This overwrites your live config. Use with caution.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/../config" && pwd)/openclaw.json"
DEST="$HOME/.openclaw/openclaw.json"

if [ ! -f "$SRC" ]; then
    echo "ERROR: Source config not found at $SRC"
    exit 1
fi

mkdir -p "$HOME/.openclaw"
cp "$SRC" "$DEST"
echo "Deployed $SRC → $DEST"
echo ""
echo "⚠️  You still need to set secrets via CLI:"
echo '   echo "YOUR_KEY" | openclaw models auth paste-token --provider openai'
echo '   openclaw channels add telegram --token "YOUR_BOT_TOKEN"'
