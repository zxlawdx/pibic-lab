"""Sanitização de segredos antes de registrar ou exportar logs."""
from __future__ import annotations

import re
from typing import Any

_SECRET_KEYS = {
    "password",
    "passwd",
    "token",
    "secret",
    "authorization",
    "private_key",
    "passphrase",
    "elevation_password",
    "proxmox_token_secret",
}

_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(password\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(token\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(secret\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(https?://[^:/\s]+:)([^@\s]+)(@)"),
]


def redact_text(value: str) -> str:
    result = value
    for pattern in _PATTERNS:
        if pattern.groups >= 3:
            result = pattern.sub(r"\1[REDACTED]\3", result)
        else:
            result = pattern.sub(r"\1[REDACTED]", result)
    return result


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key.lower() in _SECRET_KEYS:
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value
