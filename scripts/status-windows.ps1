Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
try {
    $m = [System.Threading.Mutex]::OpenExisting("Local\ITOProjectBotNative")
    Write-Host "Native launcher is present. Confirm bot health with /status in Telegram."
    $m.Dispose()
} catch { Write-Host "Native launcher is not running. Run START_HERE.cmd." }
if (Test-Path "logs\bot.log") { Get-Content "logs\bot.log" -Tail 50 }
