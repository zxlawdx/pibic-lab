#!/bin/sh
set -eu

BASE="/opt/pibic-workspace/web"
JS_DIR="$BASE/js"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="/opt/pibic-workspace/backups/refresh-fix-$STAMP"

if [ ! -d "$JS_DIR" ]; then
    echo "[ERRO] Diretorio nao encontrado: $JS_DIR"
    exit 1
fi

mkdir -p "$BACKUP"
cp -a "$JS_DIR" "$BACKUP/js"
find "$BASE" -maxdepth 2 -type f -name '*.html' -exec cp -p '{}' "$BACKUP/" \; 2>/dev/null || true

echo "=================================================="
echo "PIBIC WORKSPACE - HOTFIX DE REFRESH"
echo "=================================================="
echo "Backup: $BACKUP"
echo

python3 - <<'PY'
from pathlib import Path
import re

base = Path('/opt/pibic-workspace/web')
js_dir = base / 'js'
changed = []
notes = []

# O problema da v3 era o Dashboard completo sendo reconstruido por timer.
# Procuramos somente timers cujo callback chama renderDashboard().
interval_patterns = [
    re.compile(
        r"setInterval\s*\(\s*\(\s*\)\s*=>\s*\{(?:(?!setInterval).){0,1800}?renderDashboard\s*\(\s*\)(?:(?!setInterval).){0,1800}?\}\s*,\s*(?:1000|2000|3000|4000|5000|10000)\s*\)\s*;?",
        re.S,
    ),
    re.compile(
        r"setInterval\s*\(\s*function\s*\([^)]*\)\s*\{(?:(?!setInterval).){0,1800}?renderDashboard\s*\(\s*\)(?:(?!setInterval).){0,1800}?\}\s*,\s*(?:1000|2000|3000|4000|5000|10000)\s*\)\s*;?",
        re.S,
    ),
]

# Alguns builds usam callback em uma unica expressao.
compact_dashboard_interval = re.compile(
    r"setInterval\s*\(\s*\(\s*\)\s*=>\s*(?:[^;\n]{0,500})?renderDashboard\s*\(\s*\)\s*,\s*(?:1000|2000|3000|4000|5000|10000)\s*\)\s*;?",
    re.S,
)

# O relogio mostra apenas HH:MM, entao 1 s nao tem utilidade.
clock_interval = re.compile(
    r"(setInterval\s*\(\s*\(\s*\)\s*=>\s*\{(?:(?!setInterval).){0,900}?(?:topClock|clock)(?:(?!setInterval).){0,900}?\}\s*,\s*)1000(\s*\)\s*;?)",
    re.S | re.I,
)

# Se renderDashboard() escreve uma tela de Carregando antes de cada fetch,
# preservamos isso somente para a primeira renderizacao daquela view.
def patch_dashboard_loading(text: str) -> tuple[str, int]:
    starts = []
    for signature in ('async function renderDashboard', 'function renderDashboard'):
        pos = 0
        while True:
            idx = text.find(signature, pos)
            if idx < 0:
                break
            starts.append(idx)
            pos = idx + len(signature)

    if not starts:
        return text, 0

    total = 0
    out = text

    # Processa do fim para o inicio para manter indices validos.
    for start in sorted(starts, reverse=True):
        brace = out.find('{', start)
        if brace < 0:
            continue

        depth = 0
        end = None
        quote = None
        escape = False

        for i in range(brace, len(out)):
            ch = out[i]
            if quote:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == quote:
                    quote = None
                continue
            if ch in ('\"', "'", '`'):
                quote = ch
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        if end is None:
            continue

        fn = out[start:end]
        # Altera apenas atribuicoes contendo literalmente "Carregando".
        # Em refresh manual/inicial o conteudo aparece; em chamadas futuras,
        # caso a view ja esteja montada, nao apaga todo o DOM.
        pat = re.compile(
            r"(?P<lhs>(?:main|content|root|container)\.innerHTML\s*=\s*)(?P<rhs>(?:`[^`]*Carregando[^`]*`|'[^']*Carregando[^']*'|\"[^\"]*Carregando[^\"]*\"))\s*;?",
            re.S | re.I,
        )

        def repl(m):
            nonlocal total
            total += 1
            return f"if (!{m.group('lhs').split('.')[0]}.innerHTML.trim()) {m.group('lhs')}{m.group('rhs')};"

        new_fn = pat.sub(repl, fn)
        out = out[:start] + new_fn + out[end:]

    return out, total

for path in sorted(js_dir.glob('*.js')):
    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        continue

    original = text
    removed = 0

    for pattern in interval_patterns:
        text, n = pattern.subn(
            "/* PIBIC hotfix: full Dashboard auto-render removido; dados nao devem destruir/recriar a view por timer. */",
            text,
        )
        removed += n

    text, n = compact_dashboard_interval.subn(
        "/* PIBIC hotfix: full Dashboard auto-render removido. */",
        text,
    )
    removed += n

    text, clock_n = clock_interval.subn(r"\g<1>60000\g<2>", text)
    text, loading_n = patch_dashboard_loading(text)

    if text != original:
        path.write_text(text, encoding='utf-8')
        changed.append(path.name)
        notes.append((path.name, removed, clock_n, loading_n))

print('[INFO] Arquivos JS alterados:', ', '.join(changed) if changed else 'nenhum')
for name, removed, clock_n, loading_n in notes:
    print(f'  {name}: timers dashboard removidos={removed}, relogio 1s->60s={clock_n}, loading protegido={loading_n}')

if not changed:
    raise SystemExit('[ERRO] Nenhum padrao conhecido foi encontrado. Nada foi alterado.')

# Cache bust dos assets da v3 para o Chrome nao reutilizar o JS anterior.
for html in base.rglob('*.html'):
    try:
        s = html.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        continue
    old = s
    s = s.replace('?v=3.0.0', '?v=3.0.1')
    s = s.replace('?v=3.0', '?v=3.0.1')
    if s != old:
        html.write_text(s, encoding='utf-8')
        print('[OK] Cache bust:', html)
PY

echo
echo "Reiniciando somente o servico web..."
if ! rc-service pibic-workspace restart; then
    echo "[ERRO] Falha ao reiniciar o Workspace. Restaurando JS..."
    rm -rf "$JS_DIR"
    cp -a "$BACKUP/js" "$JS_DIR"
    rc-service pibic-workspace restart || true
    exit 1
fi

sleep 2

echo
echo "===== HEALTH ====="
if wget -qO- -T 5 http://127.0.0.1:8765/api/health; then
    echo
    echo
    echo "=================================================="
    echo "HOTFIX APLICADO"
    echo "=================================================="
    echo "- Dashboard nao sera mais reconstruido por timer"
    echo "- Tela de Carregando nao deve piscar periodicamente"
    echo "- Relogio de HH:MM deixa de rodar a cada 1 segundo quando detectado"
    echo "- SSH nao foi alterado"
    echo "- ZeroTier nao foi alterado"
    echo "- VM nao foi reiniciada"
    echo "- Backup: $BACKUP"
    echo
    echo "Feche e reabra a aba do navegador ou faca recarga completa."
else
    echo
    echo "[ERRO] Health check falhou. Restaurando backup..."
    rm -rf "$JS_DIR"
    cp -a "$BACKUP/js" "$JS_DIR"
    rc-service pibic-workspace restart || true
    exit 1
fi
