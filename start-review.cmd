@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-review.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. Please read the message above.
  pause
  exit /b 1
)
