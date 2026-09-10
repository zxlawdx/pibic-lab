"""Diagnóstico rápido do ambiente local do PIBIC LAB."""
from __future__ import annotations

import importlib
import platform
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODULES = [
    "vela",
    "asyncssh",
    "keyring",
    "pydantic",
    "yaml",
    "requests",
    "socks",
    "platformdirs",
]


def main() -> int:
    failures = 0
    print("PIBIC LAB - verificação de ambiente")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Sistema: {platform.platform()}")
    print(f"Projeto: {ROOT}")
    print()

    if sys.version_info < (3, 12):
        print("[ERRO] Python 3.12+ é recomendado para este projeto.")
        failures += 1
    else:
        print("[OK] Python compatível")

    for module in MODULES:
        try:
            imported = importlib.import_module(module)
            version = getattr(imported, "__version__", "instalado")
            print(f"[OK] {module}: {version}")
        except Exception as exc:
            print(f"[ERRO] {module}: {exc}")
            failures += 1

    print(f"[INFO] ZeroTier CLI: {shutil.which('zerotier-cli') or 'não encontrado no PATH'}")

    # O collectstatic do Vela já cria staticfiles/<nome_do_app>/.
    # Portanto apps/lab/static/lab/ seria uma duplicação e faria a UI
    # procurar /static/lab/... enquanto os arquivos acabariam em /lab/lab/....
    nested_static = ROOT / "apps" / "lab" / "static" / "lab"
    if nested_static.exists():
        print("[ERRO] Estrutura estática duplicada: apps/lab/static/lab/. Use apps/lab/static/css, js e vendor diretamente.")
        failures += 1
    else:
        print("[OK] Estrutura de estáticos do app está correta")

    required_source = [
        ROOT / "apps" / "lab" / "static" / "css" / "app.css",
        ROOT / "apps" / "lab" / "static" / "js" / "icons.js",
        ROOT / "apps" / "lab" / "static" / "js" / "app.js",
    ]
    for asset in required_source:
        if asset.exists() and asset.stat().st_size > 0:
            print(f"[OK] Asset fonte: {asset.relative_to(ROOT)}")
        else:
            print(f"[ERRO] Asset fonte ausente: {asset.relative_to(ROOT)}")
            failures += 1

    collected_css = ROOT / "staticfiles" / "lab" / "css" / "app.css"
    if collected_css.exists() and collected_css.stat().st_size > 0:
        print("[OK] CSS coletado: staticfiles/lab/css/app.css")
    else:
        print("[ERRO] CSS não foi coletado. Rode: python manage.py collectstatic --noinput")
        failures += 1

    xterm = ROOT / "apps" / "lab" / "static" / "vendor" / "xterm" / "xterm.js"
    print(f"[INFO] xterm.js local: {'presente' if xterm.exists() and xterm.stat().st_size > 1000 else 'placeholder; fallback básico será usado'}")

    # Verifica a correção do ciclo de vida da UI. O Vela injeta a view depois
    # de DOMContentLoaded, então o app.js precisa conseguir iniciar imediatamente.
    app_js = (ROOT / "apps" / "lab" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    if "document.readyState === 'loading'" in app_js and "__PIBIC_LAB_ACTIVE_ROOT__" in app_js:
        print("[OK] Bootstrap do frontend compatível com navegação dinâmica do Vela")
    else:
        print("[ERRO] Bootstrap do frontend está desatualizado; os botões podem não responder")
        failures += 1

    compat = ROOT / "pibic_lab_core" / "vela_compat.py"
    if compat.exists():
        print("[OK] Camada de compatibilidade Vela/GTK presente")
    else:
        print("[ERRO] Camada de compatibilidade Vela/GTK ausente")
        failures += 1

    try:
        from vela.core.bridge import BaseBridge
        print(f"[INFO] Vela BaseBridge.get_config nativo: {hasattr(BaseBridge, 'get_config')}")
    except Exception as exc:
        print(f"[AVISO] Não foi possível inspecionar BaseBridge: {exc}")

    print()
    print("Ambiente pronto." if not failures else f"Foram encontradas {failures} pendência(s).")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
