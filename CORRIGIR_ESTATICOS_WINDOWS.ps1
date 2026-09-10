$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "PIBIC LAB - correção da estrutura de arquivos estáticos"

if (Test-Path "apps\lab\static\lab") {
    Write-Host "Corrigindo namespace duplicado apps/lab/static/lab/..."
    Get-ChildItem "apps\lab\static\lab" -Force | ForEach-Object {
        Copy-Item $_.FullName "apps\lab\static" -Recurse -Force
    }
    Remove-Item "apps\lab\static\lab" -Recurse -Force
}

$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

& $python -c @'
from pathlib import Path
root = Path.cwd()
for rel in ("scripts/vendor_frontend.py", "scripts/check_environment.py"):
    p = root / rel
    if not p.exists():
        continue
    text = p.read_text(encoding="utf-8")
    text = text.replace(
        'ROOT / "apps" / "lab" / "static" / "lab" / "vendor" / "xterm"',
        'ROOT / "apps" / "lab" / "static" / "vendor" / "xterm"',
    )
    p.write_text(text, encoding="utf-8")
'@

Remove-Item staticfiles -Recurse -Force -ErrorAction SilentlyContinue
& $python scripts\vendor_frontend.py
& $python manage.py collectstatic --noinput
& $python scripts\check_environment.py

Write-Host ""
Write-Host "Correção concluída. Agora execute: $python manage.py runapp"
