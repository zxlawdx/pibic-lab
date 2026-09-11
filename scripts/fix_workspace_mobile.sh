#!/bin/sh
set -eu

JS="/opt/pibic-workspace/web/js/desktop.js"
CSS="/opt/pibic-workspace/web/css/app.css"
SERVICE="pibic-workspace"
STAMP="$(date +%Y%m%d-%H%M%S)"

printf '\n==================================================\n'
printf 'PIBIC WORKSPACE - PATCH MOBILE\n'
printf '==================================================\n\n'

if [ "$(id -u)" -ne 0 ]; then
    echo "[ERRO] Execute com: doas sh /tmp/fix_workspace_mobile.sh"
    exit 1
fi

for file in "$JS" "$CSS"; do
    if [ ! -f "$file" ]; then
        echo "[ERRO] Arquivo não encontrado: $file"
        exit 1
    fi
done

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERRO] python3 não encontrado. O Workspace deveria possuir Python 3."
    exit 1
fi

echo "[1/5] Criando backups..."
cp "$JS" "${JS}.bak-${STAMP}"
cp "$CSS" "${CSS}.bak-${STAMP}"

export PIBIC_PATCH_STAMP="$STAMP"

python3 <<'PY'
from pathlib import Path
import re

js = Path('/opt/pibic-workspace/web/js/desktop.js')
css = Path('/opt/pibic-workspace/web/css/app.css')

s = js.read_text(encoding='utf-8')

old = """renderDesktop();
desktopArea.addEventListener('dblclick',e=>{const b=e.target.closest('[data-app]');if(b)openApp(b.dataset.app)});desktopArea.addEventListener('click',e=>{desktopArea.querySelectorAll('.desktop-icon').forEach(x=>x.classList.remove('selected'));e.target.closest('[data-app]')?.classList.add('selected')});
$('#favorite-apps').addEventListener('click',e=>{const b=e.target.closest('[data-fav]');if(b)openApp(b.dataset.fav)});"""

new = """renderDesktop();
desktopArea.addEventListener('click',e=>{
  const b=e.target.closest('[data-app]');
  desktopArea.querySelectorAll('.desktop-icon').forEach(x=>x.classList.remove('selected'));
  if(!b)return;
  b.classList.add('selected');
  openApp(b.dataset.app);
});
desktopArea.addEventListener('dblclick',e=>{
  const b=e.target.closest('[data-app]');
  if(b)openApp(b.dataset.app);
});
desktopArea.addEventListener('keydown',e=>{
  const b=e.target.closest('[data-app]');
  if(!b)return;
  if(e.key==='Enter' || e.key===' '){
    e.preventDefault();
    openApp(b.dataset.app);
  }
});
$('#favorite-apps').addEventListener('click',e=>{const b=e.target.closest('[data-fav]');if(b)openApp(b.dataset.fav)});"""

if old in s:
    s = s.replace(old, new, 1)
    print('[OK] Clique simples e teclado aplicados ao desktop.')
elif "desktopArea.addEventListener('keydown',e=>{" in s and "openApp(b.dataset.app);" in s:
    print('[OK] Patch de clique/teclado já estava aplicado.')
else:
    print('[AVISO] Trecho original do desktop.js não foi encontrado; JS mantido sem alteração nessa parte.')

js.write_text(s, encoding='utf-8')

c = css.read_text(encoding='utf-8')

# Garante rolagem do desktop, independentemente da minificação/ordem da regra.
match = re.search(r"\.desktop-area\{([^}]*)\}", c)
if match:
    body = match.group(1)
    if 'overflow:auto' not in body.replace(' ', ''):
        replacement = '.desktop-area{' + body.rstrip(';') + ';overflow:auto}'
        c = c[:match.start()] + replacement + c[match.end():]
        print('[OK] Scroll do desktop habilitado.')
    else:
        print('[OK] Scroll do desktop já estava habilitado.')
else:
    print('[AVISO] Regra .desktop-area não encontrada.')

marker = '/* PIBIC MOBILE DESKTOP FIX v2 */'
extra = r'''
/* PIBIC MOBILE DESKTOP FIX v2 */
@media(max-width:1100px){
  .desktop-area{grid-template-columns:repeat(auto-fill,80px);grid-auto-rows:84px;padding:14px;gap:8px;overflow:auto}
  .desktop-icon{width:80px;height:80px}
  .desktop-icon svg{width:30px;height:30px}
  .desktop-icon span{font-size:11px;max-width:72px}
  .taskbar{height:48px;padding:4px 8px}
  .taskbar-button{width:36px;height:36px}
}

@media(max-height:780px){
  :root{--topbar:40px;--taskbar:48px}
  .desktop-area{padding:12px;grid-template-columns:repeat(auto-fill,76px);grid-auto-rows:80px;gap:8px;overflow:auto}
  .desktop-icon{width:76px;height:76px;gap:5px}
  .desktop-icon svg{width:28px;height:28px}
  .desktop-icon span{font-size:11px;max-width:68px}
  .taskbar{height:48px;padding:4px 8px}
  .taskbar-button{width:36px;height:36px}
  .launcher{left:8px;right:8px;bottom:calc(var(--taskbar) + 8px);width:auto;max-height:min(420px,calc(100vh - 100px));overflow:auto}
  .quick-status{right:8px;top:calc(var(--topbar) + 6px);width:min(300px,calc(100vw - 16px))}
  .notification-center{right:8px;left:8px;bottom:calc(var(--taskbar) + 8px);width:auto;max-height:300px;overflow:auto}
}

@media(max-width:640px){
  .desktop-area{padding:10px;grid-template-columns:repeat(auto-fill,minmax(70px,1fr));grid-auto-rows:78px;gap:6px}
  .desktop-icon{width:100%;max-width:78px;height:74px;justify-self:center}
  .desktop-icon svg{width:27px;height:27px}
  .desktop-icon span{font-size:10px;max-width:68px}
  .window{max-width:calc(100vw - 8px)!important;max-height:calc(100vh - var(--topbar) - var(--taskbar) - 8px)!important}
}
'''

if marker not in c:
    c += '\n' + extra.strip() + '\n'
    print('[OK] Regras responsivas adicionadas.')
else:
    print('[OK] Regras responsivas já estavam presentes.')

css.write_text(c, encoding='utf-8')
PY

echo "[2/5] Validando arquivos..."
python3 - <<'PY'
from pathlib import Path
for p in [Path('/opt/pibic-workspace/web/js/desktop.js'), Path('/opt/pibic-workspace/web/css/app.css')]:
    if not p.exists() or p.stat().st_size < 100:
        raise SystemExit(f'[ERRO] Arquivo inválido: {p}')
print('[OK] Arquivos validados.')
PY

echo "[3/5] Reiniciando somente o serviço pibic-workspace..."
rc-service "$SERVICE" restart

echo "[4/5] Aguardando serviço..."
sleep 1

echo "[5/5] Health check..."
if command -v wget >/dev/null 2>&1; then
    HEALTH="$(wget -qO- -T 5 http://127.0.0.1:8765/api/health 2>/dev/null || true)"
elif command -v curl >/dev/null 2>&1; then
    HEALTH="$(curl -fsS --max-time 5 http://127.0.0.1:8765/api/health 2>/dev/null || true)"
else
    HEALTH="$(python3 - <<'PY'
import urllib.request
try:
    print(urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=5).read().decode())
except Exception:
    pass
PY
)"
fi

if [ -z "$HEALTH" ]; then
    echo "[ERRO] O serviço não respondeu ao health check."
    echo "Restaurando backups desta execução..."
    cp "${JS}.bak-${STAMP}" "$JS"
    cp "${CSS}.bak-${STAMP}" "$CSS"
    rc-service "$SERVICE" restart || true
    echo "[ROLLBACK] Arquivos anteriores restaurados."
    exit 1
fi

printf '\n==================================================\n'
printf 'PATCH APLICADO COM SUCESSO\n'
printf '==================================================\n'
printf 'Health: %s\n' "$HEALTH"
printf 'Bind: 127.0.0.1:8765\n'
printf 'SSH: NÃO ALTERADO\n'
printf 'ZeroTier: NÃO ALTERADO\n'
printf 'VM: NÃO REINICIADA\n'
printf 'Backups: %s e %s\n' "${JS}.bak-${STAMP}" "${CSS}.bak-${STAMP}"
printf '==================================================\n'
