"""Caminhos de dados do aplicativo, independentes do diretório de execução."""
from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir, user_log_dir

APP_NAME = "PIBIC LAB"
APP_AUTHOR = "UNIR PIBIC"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    override = os.getenv("PIBIC_LAB_DATA_DIR", "").strip()
    path = Path(override).expanduser() if override else Path(user_data_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    override = os.getenv("PIBIC_LAB_DATA_DIR", "").strip()
    path = (Path(override).expanduser() / "logs") if override else Path(user_log_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / "pibic_lab.sqlite3"


def known_hosts_path() -> Path:
    return data_dir() / "known_hosts"


def diagnostics_dir() -> Path:
    path = data_dir() / "diagnostics"
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundled_catalog_dir() -> Path:
    return PROJECT_ROOT / "catalog" / "manifests"
