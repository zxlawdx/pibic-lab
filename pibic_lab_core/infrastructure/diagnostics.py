"""Exportação de diagnóstico sem segredos."""
from __future__ import annotations

import json
import platform
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

from pibic_lab_core.security.redaction import redact
from pibic_lab_core.util.paths import diagnostics_dir


class DiagnosticsExporter:
    def __init__(self, store, audit) -> None:
        self.store = store
        self.audit = audit

    def export(self, runtime: dict[str, Any]) -> Path:
        out_dir = diagnostics_dir()
        stem = "pibic-lab-diagnostico"
        json_path = out_dir / f"{stem}.json"
        zip_path = out_dir / f"{stem}.zip"
        payload = {
            "platform": {
                "python": sys.version,
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
            },
            "environments": [e.model_dump() for e in self.store.list_environments()],
            "profiles": [p.model_dump() for p in self.store.list_profiles()],
            "settings": self.store.get_settings().model_dump(),
            "runtime": runtime,
            "audit": self.audit.recent(300),
        }
        json_path.write_text(json.dumps(redact(payload), ensure_ascii=False, indent=2), encoding="utf-8")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(json_path, arcname=json_path.name)
            if self.audit.path.exists():
                # Eventos já são sanitizados no momento da escrita.
                archive.write(self.audit.path, arcname="audit.jsonl")
        try:
            json_path.unlink()
        except OSError:
            pass
        return zip_path
