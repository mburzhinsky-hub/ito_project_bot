$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Host "Container status:" -ForegroundColor Cyan
docker compose ps
Write-Host ""
Write-Host "Last 100 log lines:" -ForegroundColor Cyan
docker compose logs --tail 100 bot
