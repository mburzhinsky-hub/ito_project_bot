$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$backupDir = "backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $backupDir "bot-$stamp.db"

if (-not (Test-Path "data\bot.db")) {
    throw "data\bot.db was not found. The bot may not have started yet."
}

Write-Host "Stopping the bot briefly for a consistent SQLite backup..." -ForegroundColor Cyan
docker compose stop bot
try {
    Copy-Item "data\bot.db" $target
    Write-Host "Backup created: $target" -ForegroundColor Green
}
finally {
    docker compose start bot
}
