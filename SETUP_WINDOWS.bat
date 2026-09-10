@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1"
if errorlevel 1 (
  echo.
  echo A preparacao falhou. Leia a mensagem acima.
  pause
  exit /b 1
)
pause
