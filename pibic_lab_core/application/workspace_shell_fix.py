"""Correções de quoting dos comandos shell do Workspace multiusuário.

O launcher executa um script com ``sh -c '...'``. Portanto, aspas simples
embutidas em trechos enviados ao ``python -c`` encerram prematuramente o
argumento do shell externo. Este módulo corrige somente esses trechos sem
alterar a lógica de isolamento por usuário.
"""
from __future__ import annotations

from types import ModuleType
from typing import Callable


def _fix_python_shell_quotes(command: str) -> str:
    """Escapa aspas do Python para sobreviver ao ``sh -c '...'`` externo."""
    return (
        command
        .replace(
            "s.bind(('127.0.0.1', 0))",
            's.bind((\\"127.0.0.1\\", 0))',
        )
        .replace(
            "urllib.request.urlopen('http://127.0.0.1:$PORT/api/health', timeout=2)",
            'urllib.request.urlopen(\\"http://127.0.0.1:$PORT/api/health\\", timeout=2)',
        )
        .replace(
            "'pibic-workspace' in data",
            '\\"pibic-workspace\\" in data',
        )
    )


def apply_workspace_shell_fix(workspace_module: ModuleType) -> None:
    """Aplica o hotfix uma única vez às fábricas de comando do Workspace."""
    if getattr(workspace_module, "_shell_quote_fix_installed", False):
        return

    original_probe: Callable[[], str] = workspace_module._probe_command
    original_start: Callable[[str], str] = workspace_module._start_command

    def fixed_probe_command() -> str:
        return _fix_python_shell_quotes(original_probe())

    def fixed_start_command(access_token: str) -> str:
        return _fix_python_shell_quotes(original_start(access_token))

    workspace_module._probe_command = fixed_probe_command
    workspace_module._start_command = fixed_start_command
    workspace_module._shell_quote_fix_installed = True
