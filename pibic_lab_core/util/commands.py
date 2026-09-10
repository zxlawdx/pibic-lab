"""Comandos remotos permitidos e validadores de argumentos dinâmicos.

Somente IDs pré-definidos entram no catálogo/detectores. Argumentos dinâmicos
passam por validação estrita antes de compor um comando remoto.
"""
from __future__ import annotations

import re
import shlex

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
SAFE_PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,127}$")

FIXED_COMMANDS: dict[str, str] = {
    "os_release": "cat /etc/os-release 2>/dev/null || true",
    "kernel": "uname -r 2>/dev/null || true",
    "hostname": "hostname 2>/dev/null || true",
    "arch": "uname -m 2>/dev/null || true",
    "cpu_count": "nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || true",
    "cpu_model": "awk -F: '/model name|Hardware|Processor/ {gsub(/^ +/,\"\",$2); print $2; exit}' /proc/cpuinfo 2>/dev/null || true",
    "meminfo": "cat /proc/meminfo 2>/dev/null || true",
    "disk_root": "df -B1 -P / 2>/dev/null | tail -n 1 || true",
    "ip_addresses": "hostname -I 2>/dev/null || ip -o -4 addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | tr '\\n' ' ' || true",
    "uptime": "cut -d. -f1 /proc/uptime 2>/dev/null || true",
    "id_u": "id -u 2>/dev/null || true",
    "sudo_check": "command -v sudo >/dev/null 2>&1 && echo yes || echo no",
    "doas_check": "command -v doas >/dev/null 2>&1 && echo yes || echo no",
    "git": "command -v git >/dev/null 2>&1 && git --version || true",
    "python": "command -v python3 >/dev/null 2>&1 && python3 --version 2>&1 || true",
    "node": "command -v node >/dev/null 2>&1 && node --version || true",
    "docker": "command -v docker >/dev/null 2>&1 && docker --version || true",
    "compose": "command -v docker >/dev/null 2>&1 && docker compose version 2>/dev/null || true",
    "postgresql": "command -v psql >/dev/null 2>&1 && psql --version || true",
    "nginx": "command -v nginx >/dev/null 2>&1 && nginx -v 2>&1 || true",
    "apache": "(command -v apache2 >/dev/null 2>&1 && apache2 -v 2>&1 | head -n 1) || (command -v httpd >/dev/null 2>&1 && httpd -v 2>&1 | head -n 1) || true",
    "ssh_server": "(ss -lnt 2>/dev/null || netstat -lnt 2>/dev/null || true) | grep -E '(:22[[:space:]]|:22$)' | head -n 1 || true",
    "docker_ps_json": "docker ps -a --format '{{json .}}'",
    "docker_info": "docker info --format '{{json .ServerVersion}}'",
    "compose_ls_json": "docker compose ls --format json 2>/dev/null || true",
}


def fixed(command_id: str) -> str:
    try:
        return FIXED_COMMANDS[command_id]
    except KeyError as exc:
        raise ValueError(f"Comando não permitido: {command_id}") from exc


def validate_identifier(value: str, label: str = "identificador") -> str:
    if not SAFE_ID.fullmatch(value):
        raise ValueError(f"{label} contém caracteres não permitidos")
    return value


def validate_packages(packages: list[str]) -> list[str]:
    if not packages:
        raise ValueError("Lista de pacotes vazia")
    for package in packages:
        if not SAFE_PACKAGE.fullmatch(package):
            raise ValueError(f"Pacote inválido: {package}")
    return packages


def quote_args(args: list[str]) -> str:
    return " ".join(shlex.quote(item) for item in args)
