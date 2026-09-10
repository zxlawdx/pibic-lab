$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "PIBIC LAB - preparação do ambiente Windows"

function Find-Python {
    $candidates = @(
        @{ Cmd = "py"; Args = @("-3.13") },
        @{ Cmd = "py"; Args = @("-3.12") },
        @{ Cmd = "python"; Args = @() }
    )
    foreach ($candidate in $candidates) {
        try {
            & $candidate.Cmd @($candidate.Args) -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch {}
    }
    throw "Python 3.12 ou superior não foi encontrado. Instale o Python e marque a opção de adicionar ao PATH."
}

$python = Find-Python
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Criando ambiente virtual .venv..."
    & $python.Cmd @($python.Args) -m venv .venv
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
Write-Host "Atualizando ferramentas de instalação..."
& $venvPython -m pip install --upgrade pip setuptools wheel

Write-Host "Instalando dependências do aplicativo..."
& $venvPython -m pip install -r requirements.txt

Write-Host "Preparando xterm.js para uso local..."
& $venvPython scripts\vendor_frontend.py

Write-Host "Coletando arquivos estáticos do Vela..."
Remove-Item staticfiles -Recurse -Force -ErrorAction SilentlyContinue
& $venvPython manage.py collectstatic --noinput

Write-Host "Executando diagnóstico..."
& $venvPython scripts\check_environment.py

Write-Host ""
Write-Host "Preparação concluída. Use INICIAR_WINDOWS.bat para abrir o PIBIC LAB."
