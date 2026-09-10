#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  ./setup_linux.sh
fi

echo "PIBIC LAB - preparando interface..."
.venv/bin/python manage.py collectstatic --noinput >/dev/null
.venv/bin/python scripts/check_environment.py

echo
echo "Abrindo PIBIC LAB..."
exec .venv/bin/python manage.py runapp
