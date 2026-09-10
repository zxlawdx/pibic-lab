#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "PIBIC LAB - correção da estrutura de arquivos estáticos"

if [ -d "apps/lab/static/lab" ]; then
  echo "Corrigindo namespace duplicado apps/lab/static/lab/..."
  mkdir -p apps/lab/static
  cp -a apps/lab/static/lab/. apps/lab/static/
  rm -rf apps/lab/static/lab
fi

python_bin="python"
if [ -x ".venv/bin/python" ]; then
  python_bin=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  python_bin="python3"
fi

"$python_bin" - <<'PY'
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
PY

rm -rf staticfiles
"$python_bin" scripts/vendor_frontend.py || true
"$python_bin" manage.py collectstatic --noinput
"$python_bin" scripts/check_environment.py || true

echo
echo "Correção concluída. Agora execute:"
echo "  $python_bin manage.py runapp"
