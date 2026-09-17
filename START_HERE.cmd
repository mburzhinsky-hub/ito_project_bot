@echo off
setlocal
cd /d "%~dp0"
title ITO Project Bot Setup

echo ============================================================
echo  ITO PROJECT BOT - AUTOMATIC SETUP
echo ============================================================
echo.
echo This script will install Python if needed, ask for two
echo secret keys, check the APIs, and start the bot without Docker.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-windows.ps1"
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" (
  echo ============================================================
  echo SETUP FAILED. Do not close this window yet.
  echo Send the error text above to ChatGPT.
  echo ============================================================
) else (
  echo ============================================================
  echo SETUP FINISHED SUCCESSFULLY.
  echo Next: configure BotFather, add the bot to a group, run /setup.
  echo ============================================================
)
echo.
pause
exit /b %EXITCODE%
