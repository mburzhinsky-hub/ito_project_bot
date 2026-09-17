$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$mutex = New-Object System.Threading.Mutex($false, "Local\ITOProjectBotNative")
$owned = $false
try {
    try { $owned = $mutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $owned = $true }
    if (-not $owned) { exit 0 }
    $python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) { throw "Run START_HERE.cmd first." }
    New-Item -ItemType Directory -Force -Path "logs" | Out-Null
    Write-Host "ITO Bot is running. Minimize this window; closing it stops the bot."
    Write-Host "Logs: logs\bot.log. Automatic retry after process failure."
    while ($true) {
        if ((Test-Path "logs\bot.log") -and (Get-Item "logs\bot.log").Length -gt 10MB) {
            Move-Item -Force "logs\bot.log" "logs\bot.previous.log"
        }
        & $python -u -m app.main >> "logs\bot.log" 2>&1
        Write-Host "Bot process exited. Retrying in 15 seconds."
        Start-Sleep -Seconds 15
    }
}
finally {
    if ($owned) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
