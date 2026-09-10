"""Auditoria estruturada local, sempre sanitizada."""
from __future__ import annotations

import json
import threading
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from pibic_lab_core.domain.models import AuditEvent
from pibic_lab_core.security.redaction import redact


class AuditService:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.log_dir / "audit.jsonl"
        self._lock = threading.RLock()

    def log(
        self,
        category: str,
        action: str,
        actor: str,
        *,
        target: str | None = None,
        outcome: str = "ok",
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            id=uuid.uuid4().hex,
            category=category,
            action=action,
            actor=actor,
            target=target,
            outcome=outcome,
            details=redact(details or {}),
        )
        line = json.dumps(event.model_dump(), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return event

    def recent(self, limit: int = 200) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self._lock:
            with self.path.open("r", encoding="utf-8", errors="replace") as handle:
                lines = deque(handle, maxlen=max(1, min(limit, 1000)))
        result = []
        for line in lines:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(result))
