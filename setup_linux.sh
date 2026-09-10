#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "PIBIC LAB - preparação do ambiente Linux"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERRO: python3 não encontrado. Instale Python 3.12 ou superior."
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("ERRO: Python 3.12 ou superior é necessário.")
print("Python compatível:", sys.version.split()[0])
PY

if ! python3 - <<'PY' >/dev/null 2>&1
import gi
PY
then
  cat <<'MSG'
AVISO: PyGObject/GTK não foi detectado no Python do sistema.
No Linux Mint/Ubuntu/Debian, normalmente você pode instalar os componentes com:
  sudo apt update
  sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1
Depois execute este script novamente.
MSG
fi

if [ ! -x .venv/bin/python ]; then
  echo "Criando .venv com acesso aos pacotes GTK do sistema..."
  python3 -m venv .venv --system-site-packages
fi

.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/vendor_frontend.py
rm -rf staticfiles
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python scripts/check_environment.py || true

echo
echo "Preparação concluída. Execute ./iniciar_linux.sh"
