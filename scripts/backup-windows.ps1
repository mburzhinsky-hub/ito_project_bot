$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path "data\bot.db")) { throw "No data\bot.db found." }
New-Item -ItemType Directory -Force -Path backups | Out-Null
& ".\.venv\Scripts\python.exe" -c "import sqlite3,datetime; target='backups/bot-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.db'; src=sqlite3.connect('file:data/bot.db?mode=ro',uri=True); dst=sqlite3.connect(target); src.backup(dst); dst.close(); src.close(); print(target)"
if ($LASTEXITCODE -ne 0) { throw "Backup failed." }
