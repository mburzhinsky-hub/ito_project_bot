$ErrorActionPreference = 'Stop'
$installMutex = New-Object System.Threading.Mutex($false, 'Local\ITOProjectBotInstaller')
$owned = $false
try {
    try { $owned = $installMutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $owned = $true }
    if (-not $owned) { throw 'Another installer is running. Return to its window.' }
    $running = $false
    try {
        $botMutex = [System.Threading.Mutex]::OpenExisting('Local\ITOProjectBotNative')
        $botMutex.Dispose()
        $running = $true
    } catch [System.Threading.WaitHandleCannotBeOpenedException] {}
    if ($running) {
        Write-Host 'The bot launcher is already running. Check /status in Telegram.'
        Write-Host 'To reinstall, close its minimized window and run this file again.'
        exit 0
    }
    $destination = Join-Path $env:LOCALAPPDATA 'ITOProjectBot'
    # Used only by the packaging regression check; never set by the installer.
    if ($env:ITO_UNPACK_ONLY -eq '1') {
        if (-not $env:ITO_TEST_DESTINATION) { throw 'Missing test destination.' }
        $destination = $env:ITO_TEST_DESTINATION
    }
    $text = [IO.File]::ReadAllText($env:ITO_BUNDLE)
    $payload = [regex]::Match($text, '(?s)\r?\n:ITO_ARCHIVE\r?\n([A-Za-z0-9+/=\r\n]+)\z')
    if (-not $payload.Success) { throw 'Incomplete installer. Download the ZIP again.' }
    $bytes = [Convert]::FromBase64String($payload.Groups[1].Value)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $actual = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
    if ($actual -ne '__PAYLOAD_SHA256__') { throw 'Installer checksum failed. Download again.' }
    Add-Type -AssemblyName System.IO.Compression
    $stream = New-Object IO.MemoryStream(,$bytes)
    $zip = New-Object IO.Compression.ZipArchive($stream, [IO.Compression.ZipArchiveMode]::Read)
    try {
        $root = [IO.Path]::GetFullPath($destination).TrimEnd('\') + '\'
        [IO.Directory]::CreateDirectory($root) | Out-Null
        foreach ($entry in $zip.Entries) {
            $target = [IO.Path]::GetFullPath((Join-Path $root $entry.FullName))
            if (-not $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid archive path.' }
            if ($entry.FullName -match '(^|/)(\.env|data|logs|\.venv)(/|$)') { throw 'Archive contains user data.' }
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
            $inputStream = $entry.Open()
            try {
                $outputStream = [IO.File]::Create($target)
                try { $inputStream.CopyTo($outputStream) }
                finally { $outputStream.Dispose() }
            } finally { $inputStream.Dispose() }
        }
    } finally { $zip.Dispose(); $stream.Dispose() }
    Write-Host "Project extracted to: $destination"
    if ($env:ITO_UNPACK_ONLY -eq '1') { exit 0 }
    Set-Location -LiteralPath $destination
    & (Join-Path $destination 'scripts\setup-windows.ps1')
} catch {
    Write-Host ('SETUP FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
} finally {
    if ($owned) { $installMutex.ReleaseMutex() }
    $installMutex.Dispose()
}
