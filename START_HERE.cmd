@echo off
setlocal
cd /d "%~dp0"
title ITO Project Bot Setup

echo ============================================================
echo  ITO PROJECT BOT - NATIVE WINDOWS SETUP
echo ============================================================
echo.
echo No Docker. No WSL. No Windows restart is required.
echo The installer will download its own Python runtime, install
echo dependencies, ask for secret keys, and start the bot.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-native-windows.ps1"
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
  echo The bot is running in the background and will start at login.
  echo Next: disable BotFather Privacy Mode, add bot to group, /setup.
  echo ============================================================
)
echo.
pause
exit /b %EXITCODE%
