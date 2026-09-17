$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$running = $false
try {
    $m = [System.Threading.Mutex]::OpenExisting("Local\ITOProjectBotNative")
    $m.Dispose()
    $running = $true
} catch {}
if ($running) { throw "Close the minimized ITO bot window before updating, then retry." }
if ((Test-Path ".git") -and (Get-Command git -ErrorAction SilentlyContinue)) {
    & git pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "git pull failed." }
} else {
    Write-Host "ZIP installation: extract new source over this folder first. Keep .env and data."
}
& "$PSScriptRoot\setup-windows.ps1"
