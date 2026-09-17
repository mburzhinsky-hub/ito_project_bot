$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path $env:TEMP ('ITO test ' + [guid]::NewGuid().ToString())
# Include spaces, non-ASCII and shell metacharacters in the isolated paths.
$testRoot = Join-Path $testRoot ('User ' + [char]0x416 + ' & folder')
[IO.Directory]::CreateDirectory($testRoot) | Out-Null
$installer = Join-Path $testRoot 'START_HERE.cmd'
Copy-Item -LiteralPath (Join-Path $root 'dist\START_HERE.cmd') -Destination $installer
$env:ITO_UNPACK_ONLY = '1'
$env:ITO_TEST_DESTINATION = Join-Path $testRoot 'Installed App'
try {
    & $installer
    if ($LASTEXITCODE -ne 0) { throw 'Standalone CMD failed.' }
    $destination = $env:ITO_TEST_DESTINATION
    if (-not (Test-Path -LiteralPath (Join-Path $destination 'scripts\setup-windows.ps1'))) { throw 'Missing setup script.' }
    if (-not (Test-Path -LiteralPath (Join-Path $destination 'app\main.py'))) { throw 'Missing app.' }
    $installedFiles = @(Get-ChildItem -LiteralPath $destination -Recurse -File)
    if ($installedFiles.Count -ne 31) { throw 'Incomplete payload.' }
    $names = Get-Content -LiteralPath (Join-Path $root 'dist\payload-files.json') -Raw | ConvertFrom-Json
    foreach ($relative in $names) {
        $original = Join-Path $root $relative
        $a = [IO.File]::ReadAllText((Join-Path $destination $relative)).Replace("`r`n", "`n")
        $b = [IO.File]::ReadAllText($original).Replace("`r`n", "`n")
        if ($a -cne $b) { throw "Content mismatch: $relative" }
    }
    [IO.File]::WriteAllText((Join-Path $destination '.env'), 'SECRET_SENTINEL')
    [IO.Directory]::CreateDirectory((Join-Path $destination 'data')) | Out-Null
    [IO.File]::WriteAllText((Join-Path $destination 'data\bot.db'), 'DATABASE_SENTINEL')
    & $installer
    if ($LASTEXITCODE -ne 0) { throw 'Second install failed.' }
    if ([IO.File]::ReadAllText((Join-Path $destination '.env')) -ne 'SECRET_SENTINEL') { throw 'Overwrote secrets.' }
    if ([IO.File]::ReadAllText((Join-Path $destination 'data\bot.db')) -ne 'DATABASE_SENTINEL') { throw 'Overwrote database.' }
    Write-Host 'PASS: standalone extraction, all 31 files, special paths, repeat install, retained keys and database.'
} finally {
    Remove-Item Env:ITO_UNPACK_ONLY -ErrorAction SilentlyContinue
    Remove-Item Env:ITO_TEST_DESTINATION -ErrorAction SilentlyContinue
}
