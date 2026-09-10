"""Armazenamento de host keys em formato OpenSSH."""
from __future__ import annotations

from pathlib import Path


def host_pattern(host: str, port: int) -> str:
    return host if port == 22 else f"[{host}]:{port}"


def ensure_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")


def replace_host_key(path: Path, host: str, port: int, public_key: str) -> None:
    """Substitui apenas a entrada do host/porta informado.

    O usuário deve ter confirmado explicitamente a fingerprint antes desta função.
    """
    ensure_file(path)
    pattern = host_pattern(host, port)
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if not line.startswith(pattern + " ")]
    kept.append(f"{pattern} {public_key.strip()}")
    path.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")


def find_host_key_line(path: Path, host: str, port: int) -> str | None:
    ensure_file(path)
    pattern = host_pattern(host, port)
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(pattern + " "):
            return line
    return None
