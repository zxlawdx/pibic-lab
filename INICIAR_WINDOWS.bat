@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente ainda nao preparado. Executando o setup inicial...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1"
  if errorlevel 1 pause & exit /b 1
)

echo PIBIC LAB - preparando interface...
".venv\Scripts\python.exe" manage.py collectstatic --noinput >nul
if errorlevel 1 (
  echo Falha ao coletar os arquivos estaticos.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" scripts\check_environment.py
if errorlevel 1 (
  echo O diagnostico encontrou uma pendencia que impede uma inicializacao confiavel.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" manage.py runapp
if errorlevel 1 (
  echo.
  echo O PIBIC LAB foi encerrado com erro.
  pause
)
