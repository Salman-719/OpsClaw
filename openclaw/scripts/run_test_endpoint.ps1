# Start the test endpoint (PowerShell)
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $PSScriptRoot
$repoRoot  = Split-Path -Parent $scriptDir

Write-Host "Installing test endpoint dependencies..."
pip install -r "$scriptDir\openclaw\test_endpoint\requirements.txt" -q

Write-Host "Starting test endpoint on http://0.0.0.0:8000"
Push-Location $repoRoot
uvicorn openclaw.test_endpoint.test_endpoint:app --host 0.0.0.0 --port 8000
Pop-Location
