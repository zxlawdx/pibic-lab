"""Baixa dependências web versionadas para execução 100% local no runtime.

O download acontece apenas durante o setup/build. Depois disso o aplicativo não
carrega JavaScript de CDN e funciona com os assets em static/.
"""
from __future__ import annotations

import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "apps" / "lab" / "static" / "vendor" / "xterm"

ASSETS = {
    "xterm.js": [
        "https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js",
        "https://unpkg.com/xterm@5.3.0/lib/xterm.js",
    ],
    "xterm.css": [
        "https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css",
        "https://unpkg.com/xterm@5.3.0/css/xterm.css",
    ],
    "xterm-addon-fit.js": [
        "https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js",
        "https://unpkg.com/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js",
    ],
}


def download(name: str, urls: list[str]) -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    destination = TARGET / name
    if destination.exists() and destination.stat().st_size > 1000:
        print(f"[OK] {name} já existe ({destination.stat().st_size} bytes)")
        return

    errors: list[str] = []
    for url in urls:
        try:
            print(f"[GET] {name} <- {url}")
            request = urllib.request.Request(url, headers={"User-Agent": "PIBIC-LAB-Setup/0.1"})
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read()
            if len(content) < 1000:
                raise RuntimeError("arquivo baixado é pequeno demais")
            destination.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            print(f"[OK] {name}: sha256={digest}")
            return
        except (OSError, RuntimeError, urllib.error.URLError) as exc:
            errors.append(f"{url}: {exc}")

    print(f"[AVISO] Não foi possível baixar {name}.")
    for error in errors:
        print(f"        {error}")
    print("        O app continuará com o terminal básico de contingência.")


def main() -> int:
    for name, urls in ASSETS.items():
        download(name, urls)
    return 0


if __name__ == "__main__":
    sys.exit(main())
