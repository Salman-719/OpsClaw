# Install OpenClaw on Windows (PowerShell)
$ErrorActionPreference = "Stop"

Write-Host "=== Installing OpenClaw ===" -ForegroundColor Cyan

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Node.js is required. Install from https://nodejs.org/" -ForegroundColor Red
    exit 1
}

Write-Host "Node.js $(node --version) detected"

npm install -g openclaw
npm install -g clawhub

Write-Host "=== Verifying installation ===" -ForegroundColor Cyan
openclaw --version

Write-Host ""
Write-Host "OpenClaw installed. Next steps:" -ForegroundColor Green
Write-Host "   1. Run: openclaw doctor --fix"
Write-Host "   2. Follow docs/OPENCLAW_GUIDE.md for full setup"
