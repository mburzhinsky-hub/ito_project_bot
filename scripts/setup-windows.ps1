$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
function Find-Python {
    $candidate = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path -LiteralPath $candidate) { return $candidate }
    $candidate = Join-Path $env:ProgramFiles "Python312\python.exe"
    if (Test-Path -LiteralPath $candidate) { return $candidate }
    return $null
}
Write-Host "ITO BOT - native Windows setup (no Docker)"
$python = Find-Python
if (-not $python) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "winget is unavailable. Install Python 3.12 from python.org for this user, then retry."
    }
    & winget.exe install --id Python.Python.3.12 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "Python installation failed. See the winget message above." }
    $python = Find-Python
    if (-not $python) { throw "Python 3.12 was not found after installation." }
}
$venv = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venv)) {
    & $python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create Python environment." }
}
& $venv -m pip install --disable-pip-version-check -e .
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
& $venv scripts\configure-native.py
if ($LASTEXITCODE -ne 0) { throw "Configuration or API check failed. Fix the message above and run again." }
$runner = Join-Path $PSScriptRoot "run-native.ps1"
$arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $runner + '"'
$startup = [Environment]::GetFolderPath("Startup")
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $startup "ITO Project Bot.lnk"))
$link.TargetPath = Join-Path $PSHOME "powershell.exe"
$link.Arguments = $arguments
$link.WorkingDirectory = $ProjectRoot
$link.WindowStyle = 7
$link.Save()
Start-Process -FilePath (Join-Path $PSHOME "powershell.exe") -ArgumentList $arguments -WorkingDirectory $ProjectRoot -WindowStyle Minimized
Write-Host "API checks passed. Bot launcher started; confirm with /status in Telegram."
Write-Host "Autostart enabled at Windows sign-in. Keep this folder in place."
Write-Host "Next: BotFather /setprivacy -> Disable; add bot to group; send /setup."
