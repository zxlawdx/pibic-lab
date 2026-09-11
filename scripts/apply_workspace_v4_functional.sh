#!/bin/sh
set -eu

BASE_URL="https://raw.githubusercontent.com/zxlawdx/pibic-lab/main/scripts"
BASE_PATCH="/tmp/pibic-workspace-v4-base.sh"
ROOT="${PIBIC_WS_ROOT:-/opt/pibic-workspace}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$ROOT/backups/v4-functional-fix-$STAMP"

if [ "$(id -u)" -ne 0 ]; then
  if command -v doas >/dev/null 2>&1; then
    exec doas env PIBIC_WS_ROOT="$ROOT" sh "$0"
  elif command -v sudo >/dev/null 2>&1; then
    exec sudo env PIBIC_WS_ROOT="$ROOT" sh "$0"
  else
    echo "[ERRO] Execute como root/doas/sudo."
    exit 1
  fi
fi

printf '\n==================================================\n'
printf 'PIBIC WORKSPACE v4.1 - PATCH FUNCIONAL COMPLETO\n'
printf '==================================================\n'
printf 'Alvo: %s\n' "$ROOT"
printf 'SSH/ZeroTier/rede: NAO ALTERADOS\n\n'

command -v wget >/dev/null 2>&1 || { echo '[ERRO] wget nao encontrado.'; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo '[ERRO] python3 nao encontrado.'; exit 1; }

# 1) Aplica a base v4 (APIs reais + views funcionais). Ela possui seu proprio rollback.
echo '[1/6] Aplicando base funcional v4...'
wget -qO "$BASE_PATCH" "$BASE_URL/fix_workspace_full_v4.sh"
sh "$BASE_PATCH"

JS="$ROOT/web/static/functional-v4.js"
CSS="$ROOT/web/static/functional-v4.css"
INDEX="$ROOT/web/index.html"
[ -f "$INDEX" ] || INDEX="$ROOT/web/templates/index.html"
[ -f "$JS" ] || { echo "[ERRO] $JS nao encontrado apos patch base."; exit 1; }
[ -f "$CSS" ] || { echo "[ERRO] $CSS nao encontrado apos patch base."; exit 1; }
[ -f "$INDEX" ] || { echo '[ERRO] index.html nao encontrado.'; exit 1; }

mkdir -p "$BACKUP"
cp -p "$JS" "$BACKUP/functional-v4.js"
cp -p "$CSS" "$BACKUP/functional-v4.css"
cp -p "$INDEX" "$BACKUP/index.html"
for p in "$ROOT/web/js/alpinews-v3.js" "$ROOT/web/static/js/alpinews-v3.js"; do
  if [ -f "$p" ]; then
    mkdir -p "$BACKUP/$(dirname "${p#$ROOT/}")"
    cp -p "$p" "$BACKUP/${p#$ROOT/}"
  fi
done

echo '[2/6] Corrigindo roteamento das abas e takeover da UI v3...'
export ROOT JS CSS INDEX BACKUP
python3 <<'PY'
from pathlib import Path
import os, re

root = Path(os.environ['ROOT'])
js = Path(os.environ['JS'])
css = Path(os.environ['CSS'])
index = Path(os.environ['INDEX'])

s = js.read_text(encoding='utf-8')

# Compatibilidade com o shell Alpine WS v3: ele usa data-aws-path e #aws-main.
old = "function activeNav(path){qa('aside [data-path]').forEach(a=>{const on=a.dataset.path===path;a.classList.toggle('bg-primary-container',on);a.classList.toggle('text-on-primary-container',on);a.classList.toggle('font-medium',on);a.classList.toggle('text-on-surface-variant',!on);on?a.setAttribute('aria-current','page'):a.removeAttribute('aria-current')})}"
new = "const navId=a=>a?.dataset?.awsPath||a?.dataset?.path||'';\nfunction activeNav(path){qa('#aws-shell [data-aws-path], aside [data-path]').forEach(a=>{const on=navId(a)===path;a.classList.toggle('active',on);a.classList.toggle('bg-primary-container',on);a.classList.toggle('text-on-primary-container',on);a.classList.toggle('font-medium',on);a.classList.toggle('text-on-surface-variant',!on);on?a.setAttribute('aria-current','page'):a.removeAttribute('aria-current')})}"
if old in s:
    s = s.replace(old, new, 1)
elif 'const navId=' not in s:
    raise SystemExit('[ERRO] Nao foi possivel adaptar activeNav.')

s = s.replace(
    "function setMain(html){stopView();main.innerHTML=html;window.scrollTo({top:0,behavior:'instant'})}",
    "function setMain(html){stopView();main.innerHTML=html;try{main.scrollTo({top:0,behavior:'auto'})}catch{}}",
    1,
)

s = s.replace(
    "async function route(path,push=true){path=path||'dashboard';current=path;activeNav(path);document.body.classList.remove('aws4-sidebar-open');if(push)history.pushState({aws4:path},'',`#/${path}`);const fn=routes[path]||renderInfoFallback;try{await fn(path)}catch(e){setMain(page('Falha ao carregar',path,`<div class=\"aws4-notice aws4-error\">${esc(e.message)}</div>`))}}",
    "async function route(path,push=true){path=path||'dashboard';current=path;activeNav(path);document.body.classList.remove('aws4-sidebar-open','aws-menu-open');if(push)history.pushState({aws4:path},'',`#/${path}`);const fn=routes[path]||renderInfoFallback;try{await fn(path)}catch(e){setMain(page('Falha ao carregar',path,`<div class=\"aws4-notice aws4-error\">${esc(e.message)}</div>`))}}",
    1,
)

s = s.replace(
    "function addCodeNav(){if(q('aside [data-path=\"codigo\"]'))return;const t=q('aside [data-path=\"terminal-web\"]');if(!t)return;const a=document.createElement('a');a.href='#';a.dataset.path='codigo';a.className=t.className;a.innerHTML=`${ico('code')}<span class=\"truncate\">Código</span>`;t.insertAdjacentElement('afterend',a)}",
    "function addCodeNav(){if(q('#aws-shell [data-aws-path=\"codigo\"], aside [data-path=\"codigo\"]'))return;const t=q('#aws-shell [data-aws-path=\"terminal-web\"], aside [data-path=\"terminal-web\"]');if(!t)return;const a=document.createElement('button');a.type='button';a.dataset.awsPath='codigo';a.className=t.className||'aws-nav-item';a.innerHTML=`${ico('code')}<span>Código</span>`;t.insertAdjacentElement('afterend',a)}",
    1,
)

s = s.replace(
    "function addMobileMenu(){if(q('.aws4-mobile-menu'))return;const b=document.createElement('button');b.className='aws4-mobile-menu';b.type='button';b.setAttribute('aria-label','Abrir menu');b.innerHTML=ico('menu');b.onclick=()=>document.body.classList.toggle('aws4-sidebar-open');document.body.append(b)}",
    "function addMobileMenu(){if(q('#aws-menu-btn'))return;if(q('.aws4-mobile-menu'))return;const b=document.createElement('button');b.className='aws4-mobile-menu';b.type='button';b.setAttribute('aria-label','Abrir menu');b.innerHTML=ico('menu');b.onclick=()=>document.body.classList.toggle('aws4-sidebar-open');document.body.append(b)}",
    1,
)

old_boot = "function boot(){main=q('main');if(!main)return;document.body.classList.add('aws4-ready');addCodeNav();addMobileMenu();window.addEventListener('click',e=>{const a=e.target.closest?.('aside [data-path]');if(!a)return;e.preventDefault();e.stopPropagation();route(a.dataset.path)},true);window.addEventListener('popstate',()=>route((location.hash.match(/^#\\/(.+)$/)||[])[1]||'dashboard',false));document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key.toLowerCase()==='k'&&!e.target.closest('input,textarea,.xterm,.cm-editor')){e.preventDefault();const x=prompt('Abrir módulo: dashboard, sistema, processos, armazenamento, rede, usuarios, pacotes-apk, terminal-web, codigo, docker-containers, servicos-openrc, arquivos, acesso-ssh, proxmox-cluster, rede-privada, logs-centralizados, configuracoes');if(x&&routes[x])route(x)}});const initial=(location.hash.match(/^#\\/(.+)$/)||[])[1]||'dashboard';route(initial,false)}"
new_boot = "function boot(attempt=0){const awsMain=q('#aws-main');if(window.__ALPINE_WS_V3__&&!awsMain&&attempt<40){setTimeout(()=>boot(attempt+1),50);return}main=awsMain||q('main');if(!main)return;document.body.classList.add('aws4-ready');const vb=q('#aws-version');if(vb)vb.textContent='v4.1';addCodeNav();addMobileMenu();window.addEventListener('click',e=>{const a=e.target.closest?.('#aws-shell [data-aws-path], aside [data-path]');if(!a)return;e.preventDefault();e.stopImmediatePropagation();route(navId(a))},true);window.addEventListener('popstate',()=>route((location.hash.match(/^#\\/(.+)$/)||[])[1]||'dashboard',false));document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key.toLowerCase()==='k'&&!e.target.closest('input,textarea,.xterm,.cm-editor')){e.preventDefault();const x=prompt('Abrir módulo: dashboard, sistema, processos, armazenamento, rede, usuarios, pacotes-apk, terminal-web, codigo, docker-containers, servicos-openrc, arquivos, acesso-ssh, proxmox-cluster, rede-privada, logs-centralizados, configuracoes');if(x&&routes[x])route(x)}});const initial=(location.hash.match(/^#\\/(.+)$/)||[])[1]||'dashboard';route(initial,false)}"
if old_boot in s:
    s = s.replace(old_boot, new_boot, 1)
elif "main=q('#aws-main')||q('main')" not in s and "const awsMain=q('#aws-main')" not in s:
    raise SystemExit('[ERRO] Nao foi possivel adaptar boot/roteamento.')

js.write_text(s, encoding='utf-8')

# Corrige drawer mobile sem afetar ASIDE interno do editor.
c = css.read_text(encoding='utf-8')
c = c.replace(
    "@media(max-width:900px){body.aws4-ready aside{transform:translateX(-100%);transition:transform .18s ease;box-shadow:8px 0 28px rgba(0,0,0,.35)}body.aws4-ready.aws4-sidebar-open aside{transform:translateX(0)}body.aws4-ready>div.pl-64{padding-left:0!important}body.aws4-ready header.fixed{left:0!important;padding-left:58px!important}",
    "@media(max-width:900px){body.aws4-ready .aws-sidebar{transform:translateX(-100%);transition:transform .18s ease;box-shadow:8px 0 28px rgba(0,0,0,.35)}body.aws4-ready.aws4-sidebar-open .aws-sidebar,body.aws4-ready.aws-menu-open .aws-sidebar{transform:translateX(0)}body.aws4-ready .aws-header{left:0!important}body.aws4-ready .aws-main{left:0!important}",
    1,
)
css.write_text(c, encoding='utf-8')

# O v3 continua fornecendo o shell visual, mas deixa de controlar o conteudo.
for p in (root/'web/js/alpinews-v3.js', root/'web/static/js/alpinews-v3.js'):
    if not p.exists():
        continue
    v = p.read_text(encoding='utf-8')
    v = re.sub(
        r"setInterval\s*\(\s*\(\s*\)\s*=>\s*\{\s*if\s*\(\s*\$\('\.aws-nav-item\.active'\)\?\.dataset\.awsPath\s*===\s*'dashboard'\s*\)\s*renderDashboard\(\)\.catch\(\(\)=>\{\}\)\s*\}\s*,\s*5000\s*\)\s*;?",
        "", v, flags=re.S,
    )
    v = v.replace(
        "renderDashboard().catch(e=>{$('#aws-main').innerHTML=`<div class=\"aws-dashboard\"><div class=\"aws-section aws-empty\">${esc(e.message)}</div></div>`});",
        "",
    )
    p.write_text(v, encoding='utf-8')

# Cache-bust para o celular nao reutilizar JS anterior.
h = index.read_text(encoding='utf-8')
h = re.sub(r'functional-v4\.css\?v=[^\"\']+', 'functional-v4.css?v=4.1.0', h)
h = re.sub(r'functional-v4\.js\?v=[^\"\']+', 'functional-v4.js?v=4.1.0', h)
index.write_text(h, encoding='utf-8')
PY

echo '[3/6] Validando JavaScript e Python...'
python3 -m py_compile "$ROOT/app/main.py"
if command -v node >/dev/null 2>&1; then
  node --check "$JS"
  for p in "$ROOT/web/js/alpinews-v3.js" "$ROOT/web/static/js/alpinews-v3.js"; do
    [ -f "$p" ] && node --check "$p"
  done
fi

echo '[4/6] Reiniciando SOMENTE pibic-workspace...'
if ! rc-service pibic-workspace restart; then
  echo '[ERRO] Restart falhou. Restaurando hotfix...'
  cp -p "$BACKUP/functional-v4.js" "$JS"
  cp -p "$BACKUP/functional-v4.css" "$CSS"
  cp -p "$BACKUP/index.html" "$INDEX"
  for p in "$ROOT/web/js/alpinews-v3.js" "$ROOT/web/static/js/alpinews-v3.js"; do
    rel="${p#$ROOT/}"
    [ -f "$BACKUP/$rel" ] && cp -p "$BACKUP/$rel" "$p"
  done
  rc-service pibic-workspace restart || true
  exit 1
fi
sleep 2

echo '[5/6] Testando APIs reais...'
HEALTH="$(wget -qO- -T 5 http://127.0.0.1:8765/api/health 2>/dev/null || true)"
METRICS="$(wget -qO- -T 5 http://127.0.0.1:8765/api/metrics 2>/dev/null || true)"
if [ -z "$HEALTH" ] || [ -z "$METRICS" ]; then
  echo '[ERRO] Health/metrics nao responderam.'
  exit 1
fi

printf '%s' "$METRICS" | python3 -c 'import json,sys; j=json.load(sys.stdin); d=j.get("data",j); s=d.get("system",{}); m=s.get("memory",{}); k=s.get("disk",{}); c=s.get("cpu_count",0); assert int(c or 0)>0, "cpu_count invalido"; assert int(m.get("total",0) or 0)>0, "RAM total invalida"; assert int(k.get("total",0) or 0)>0, "Disco total invalido"; print("  vCPU:",c); print("  RAM total:",m.get("total")); print("  Disco total:",k.get("total")); print("  CPU agora:",d.get("cpu_percent"),"%")'

echo '[6/6] Concluido.'
printf '\n==================================================\n'
printf 'PIBIC WORKSPACE v4.1 FUNCIONAL\n'
printf '==================================================\n'
printf 'Abas/sidebar: roteamento funcional\n'
printf 'Dashboard: CPU/RAM/Disco reais\n'
printf 'Processos/Rede/Usuarios/Armazenamento: APIs reais\n'
printf 'Terminal: PTY real\n'
printf 'Codigo: editor e execucao controlada\n'
printf 'Arquivos/APK/OpenRC/Docker/Logs: integrados\n'
printf 'Polling: silencioso, sem redesenhar a tela inteira\n'
printf 'Mobile: drawer responsivo\n'
printf 'SSH/ZeroTier/rede: NAO ALTERADOS\n'
printf 'VM: NAO REINICIADA\n'
printf 'Backup hotfix: %s\n' "$BACKUP"
printf 'Health: %s\n' "$HEALTH"
