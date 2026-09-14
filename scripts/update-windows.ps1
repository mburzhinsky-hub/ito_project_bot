$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if ((Get-Command git -ErrorAction SilentlyContinue) -and (Test-Path ".git")) {
    Write-Host "Updating source from GitHub..." -ForegroundColor Cyan
    git pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "git pull failed." }
}
else {
    Write-Host "This copy was probably downloaded as ZIP, so git pull is skipped." -ForegroundColor Yellow
    Write-Host "Download a fresh ZIP or use GitHub Desktop for future updates." -ForegroundColor Yellow
}

Write-Host "Rebuilding and restarting..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed." }
docker compose ps
Write-Host "Update complete." -ForegroundColor Green
