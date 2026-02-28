# Deploy reference config to ~/.openclaw/ (PowerShell)
# NOTE: This overwrites your live config. Use with caution.
$ErrorActionPreference = "Stop"

$src  = Join-Path $PSScriptRoot "..\config\openclaw.json"
$dest = Join-Path $env:USERPROFILE ".openclaw\openclaw.json"

if (-not (Test-Path $src)) {
    Write-Host "ERROR: Source config not found at $src" -ForegroundColor Red
    exit 1
}

New-Item -Path (Split-Path $dest) -ItemType Directory -Force | Out-Null
Copy-Item $src $dest -Force
Write-Host "Deployed $src -> $dest"
Write-Host ""
Write-Host "You still need to set secrets via CLI:" -ForegroundColor Yellow
Write-Host '   "YOUR_KEY" | openclaw models auth paste-token --provider openai'
Write-Host '   openclaw channels add telegram --token "YOUR_BOT_TOKEN"'
