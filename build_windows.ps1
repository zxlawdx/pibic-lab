$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "PIBIC LAB - build Windows"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & "$PSScriptRoot\setup_windows.ps1"
}
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

& $python -m pip install -r requirements-dev.txt
& $python scripts\vendor_frontend.py
Remove-Item staticfiles -Recurse -Force -ErrorAction SilentlyContinue
& $python manage.py collectstatic --noinput
& $python -m pytest -q

Remove-Item build, dist, package -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "PIBIC-LAB-Windows.zip" -Force -ErrorAction SilentlyContinue

$sep = ";"
$arguments = @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
    "--name", "PIBIC-LAB",
    "--add-data", "apps${sep}apps",
    "--add-data", "config${sep}config",
    "--add-data", "staticfiles${sep}staticfiles",
    "--add-data", "catalog${sep}catalog",
    "--collect-all", "vela",
    "--collect-submodules", "vela",
    "--collect-all", "asyncssh",
    "--collect-all", "keyring",
    "--collect-submodules", "keyring.backends",
    "--collect-all", "PyQt5",
    "--collect-all", "PyQtWebEngine",
    "--collect-all", "webview",
    "--collect-all", "qtpy",
    "--hidden-import", "socks",
    "--hidden-import", "webview.platforms.qt",
    "--hidden-import", "PyQt5.QtWebEngineWidgets",
    "--exclude-module", "webview.platforms.winforms",
    "--exclude-module", "clr",
    "--exclude-module", "pythonnet",
    "launcher.py"
)

& $python @arguments
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

New-Item -ItemType Directory -Force "package\PIBIC-LAB" | Out-Null
Copy-Item "dist\PIBIC-LAB\*" "package\PIBIC-LAB" -Recurse -Force
Copy-Item "README.md" "package\PIBIC-LAB\LEIA-ME.md" -Force
Copy-Item "docs\SECURITY.md" "package\PIBIC-LAB\SEGURANCA.md" -Force

Compress-Archive -Path "package\PIBIC-LAB" -DestinationPath "PIBIC-LAB-Windows.zip" -Force
Write-Host ""
Write-Host "Build concluído: PIBIC-LAB-Windows.zip"
