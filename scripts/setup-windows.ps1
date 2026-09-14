param(
    [switch]$SkipDockerInstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
    $knownDocker = Join-Path $Env:ProgramFiles "Docker\Docker\resources\bin"
    if ((Test-Path $knownDocker) -and ($env:Path -notlike "*$knownDocker*")) {
        $env:Path = "$knownDocker;$env:Path"
    }
}

function Read-SecretText([string]$Prompt) {
    $secure = Read-Host $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Test-DockerEngine {
    Refresh-Path
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        return $false
    }

    # Windows PowerShell 5.1 can convert native stderr into a terminating
    # NativeCommandError when ErrorActionPreference is Stop. Run the probe
    # through cmd.exe so a stopped Docker daemon simply returns an exit code.
    & cmd.exe /d /c "docker info >nul 2>nul"
    return ($LASTEXITCODE -eq 0)
}

function Wait-Docker {
    param([int]$Seconds = 300)
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if (Test-DockerEngine) { return $true }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Ensure-Docker {
    Refresh-Path
    if (Get-Command docker -ErrorAction SilentlyContinue) { return }
    if ($SkipDockerInstall) {
        throw "Docker was not found. Install Docker Desktop, start it, then run START_HERE.cmd again."
    }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Docker was not found and winget is unavailable. Install Docker Desktop manually, start it, then run START_HERE.cmd again."
    }

    Write-Host "Docker Desktop is not installed. Installing it with winget..." -ForegroundColor Yellow
    & winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop installation failed. If Windows requested elevation or restart, complete it and run START_HERE.cmd again."
    }

    Write-Host "Docker Desktop installation completed." -ForegroundColor Green
    Start-Sleep -Seconds 3
    Refresh-Path
}

function Test-WslAvailable {
    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
        return $false
    }
    & cmd.exe /d /c "wsl.exe --status >nul 2>nul"
    return ($LASTEXITCODE -eq 0)
}

function Start-DockerDesktop {
    $dockerExe = Join-Path $Env:ProgramFiles "Docker\Docker\Docker Desktop.exe"

    if (Test-DockerEngine) {
        Write-Host "Docker Engine is already running." -ForegroundColor Green
        return
    }

    if (-not (Test-Path $dockerExe)) {
        throw "Docker Desktop executable was not found after installation. Restart Windows and run START_HERE.cmd again."
    }

    $running = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
    if (-not $running) {
        Write-Host "Starting Docker Desktop..." -ForegroundColor Yellow
        Start-Process $dockerExe | Out-Null
    }
    else {
        Write-Host "Docker Desktop is open; waiting for the engine..." -ForegroundColor Yellow
    }

    Write-Host "Waiting for Docker Engine to become ready (up to 5 minutes)..."
    Write-Host "On the first launch Docker Desktop may open a window. Accept its first-run prompts if Windows shows them." -ForegroundColor Yellow

    if (Wait-Docker -Seconds 300) {
        Write-Host "Docker Engine is ready." -ForegroundColor Green
        return
    }

    if (-not (Test-WslAvailable)) {
        throw "Docker was installed, but WSL2 is not ready. Restart Windows first. After the restart, run START_HERE.cmd again. If Windows asks to install/update WSL, allow it."
    }

    throw "Docker Desktop is installed but its engine did not start. Open Docker Desktop, finish any first-run prompts, wait until it says Engine running, then run START_HERE.cmd again."
}

function Enable-DockerAutoStart {
    $dockerExe = Join-Path $Env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $dockerExe)) { return }
    try {
        $startup = [Environment]::GetFolderPath("Startup")
        $shortcutPath = Join-Path $startup "Docker Desktop.lnk"
        if (-not (Test-Path $shortcutPath)) {
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut($shortcutPath)
            $shortcut.TargetPath = $dockerExe
            $shortcut.WorkingDirectory = Split-Path $dockerExe
            $shortcut.Save()
        }
    }
    catch {
        Write-Host "Could not add Docker Desktop to Windows startup automatically. This is not fatal." -ForegroundColor Yellow
    }
}

function Write-EnvFile {
    if (Test-Path ".env") {
        Write-Host ".env already exists. Keeping it unchanged." -ForegroundColor Green
        return
    }

    Write-Host ""
    Write-Host "Two secret values are needed once. They stay only in the local .env file." -ForegroundColor Cyan
    $telegramToken = Read-SecretText "Paste TELEGRAM_BOT_TOKEN from BotFather"
    if ([string]::IsNullOrWhiteSpace($telegramToken)) { throw "TELEGRAM_BOT_TOKEN cannot be empty." }

    $openAiKey = Read-SecretText "Paste OPENAI_API_KEY"
    if ([string]::IsNullOrWhiteSpace($openAiKey)) { throw "OPENAI_API_KEY cannot be empty." }

    $timezone = Read-Host "Timezone [Europe/Moscow]"
    if ([string]::IsNullOrWhiteSpace($timezone)) { $timezone = "Europe/Moscow" }

    $digestTime = Read-Host "Daily digest time [18:00]"
    if ([string]::IsNullOrWhiteSpace($digestTime)) { $digestTime = "18:00" }
    if ($digestTime -notmatch '^([01]\d|2[0-3]):[0-5]\d$') { throw "Digest time must use HH:MM, for example 18:00." }

    $lines = @(
        "TELEGRAM_BOT_TOKEN=$telegramToken",
        "OPENAI_API_KEY=$openAiKey",
        "OPENAI_MODEL=gpt-5.6-luna",
        "DATABASE_URL=sqlite+aiosqlite:////app/data/bot.db",
        "DEFAULT_TIMEZONE=$timezone",
        "DEFAULT_DIGEST_TIME=$digestTime",
        "MESSAGE_RETENTION_DAYS=90",
        "UNANSWERED_QUESTION_AFTER_HOURS=12",
        "DEADLINE_REMINDER_HOURS=24",
        "LOG_LEVEL=INFO"
    )

    $content = ($lines -join [Environment]::NewLine) + [Environment]::NewLine
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Join-Path $ProjectRoot ".env"), $content, $utf8NoBom)
    Write-Host ".env created. It is excluded from Git." -ForegroundColor Green
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " ITO PROJECT BOT - AUTOMATIC WINDOWS SETUP" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

Ensure-Docker
Start-DockerDesktop
Enable-DockerAutoStart
Write-EnvFile
New-Item -ItemType Directory -Force -Path "data" | Out-Null

Write-Host ""
Write-Host "Building and starting the bot..." -ForegroundColor Cyan
& docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed." }

Write-Host ""
Write-Host "Container status:" -ForegroundColor Cyan
& docker compose ps
Write-Host ""
Write-Host "Recent bot logs:" -ForegroundColor Cyan
& docker compose logs --tail 40 bot
Write-Host ""
Write-Host "BOT IS RUNNING." -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "1. In BotFather disable Privacy Mode for the bot."
Write-Host "2. Add the bot to a Telegram project group."
Write-Host "3. In that group send: /setup"
Write-Host "4. Then send: /status"
