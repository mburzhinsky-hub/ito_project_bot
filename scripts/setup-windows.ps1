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

function Wait-Docker {
    param([int]$Seconds = 180)
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        Refresh-Path
        $docker = Get-Command docker -ErrorAction SilentlyContinue
        if ($docker) {
            & docker info *> $null
            if ($LASTEXITCODE -eq 0) { return $true }
        }
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
    Refresh-Path
}

function Start-DockerDesktop {
    $dockerExe = Join-Path $Env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Wait-Docker -Seconds 5) { return }
    if (Test-Path $dockerExe) {
        Write-Host "Starting Docker Desktop..." -ForegroundColor Yellow
        Start-Process $dockerExe | Out-Null
    }
    else {
        throw "Docker CLI is present but Docker Desktop executable was not found. Start Docker manually and run this script again."
    }
    Write-Host "Waiting for Docker Desktop to become ready (up to 3 minutes)..."
    if (-not (Wait-Docker -Seconds 180)) {
        throw "Docker Desktop did not become ready. Open Docker Desktop, finish any first-run or WSL setup, wait for Running, then run START_HERE.cmd again."
    }
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
