"""Adapter local para ZeroTier CLI sem execução arbitrária de comandos."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pibic_lab_core.domain.models import ZeroTierState

NETWORK_ID_RE = re.compile(r"^[0-9a-fA-F]{16}$")


class ZeroTierAdapter:
    def _find_cli(self) -> str | None:
        for name in ("zerotier-cli", "zerotier-cli.bat", "zerotier-cli.exe"):
            found = shutil.which(name)
            if found:
                return found

        candidates = []
        if os.name == "nt":
            candidates.extend(
                [
                    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "ZeroTier" / "One" / "zerotier-cli.bat",
                    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ZeroTier" / "One" / "zerotier-cli.bat",
                ]
            )
        else:
            candidates.extend([Path("/usr/sbin/zerotier-cli"), Path("/usr/local/sbin/zerotier-cli")])

        for path in candidates:
            if path.exists():
                return str(path)
        return None

    @staticmethod
    def _run(argv: list[str], timeout: int = 8) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )

    def status(self, network_id: str = "") -> dict[str, Any]:
        cli = self._find_cli()
        if not cli:
            return {
                "installed": False,
                "state": ZeroTierState.NOT_INSTALLED.value,
                "message": "ZeroTier não encontrado neste computador.",
                "node_id": None,
                "local_addresses": [],
                "network": None,
            }

        info = self._run([cli, "-j", "info"])
        if info.returncode != 0:
            message = (info.stderr or info.stdout or "Falha ao consultar ZeroTier").strip()
            return {
                "installed": True,
                "state": ZeroTierState.UNKNOWN.value,
                "message": message,
                "node_id": None,
                "local_addresses": [],
                "network": None,
            }

        try:
            info_json = json.loads(info.stdout or "{}")
        except json.JSONDecodeError:
            info_json = {}

        node_id = info_json.get("address")
        online = bool(info_json.get("online"))
        state = ZeroTierState.ONLINE if online else ZeroTierState.OFFLINE
        network: dict[str, Any] | None = None
        local_addresses: list[str] = []

        networks = self._run([cli, "-j", "listnetworks"])
        if networks.returncode == 0:
            try:
                items = json.loads(networks.stdout or "[]")
            except json.JSONDecodeError:
                items = []

            if network_id:
                network = next((item for item in items if str(item.get("nwid", "")).lower() == network_id.lower()), None)
            elif items:
                network = items[0]

            if network:
                status = str(network.get("status", "")).upper()
                port_error = network.get("portError")
                local_addresses = list(network.get("assignedAddresses") or [])
                if status == "ACCESS_DENIED":
                    state = ZeroTierState.ACCESS_DENIED
                elif status == "OK":
                    # TUNNELED é um indicador útil quando presente nas versões que o expõem.
                    if bool(network.get("tunneled")) or str(port_error).upper() == "TUNNELED":
                        state = ZeroTierState.TUNNELED
                    else:
                        state = ZeroTierState.OK_PRIVATE

        return {
            "installed": True,
            "state": state.value,
            "message": self._message_for(state),
            "node_id": node_id,
            "local_addresses": local_addresses,
            "network": network,
        }

    def join(self, network_id: str) -> dict[str, Any]:
        if not NETWORK_ID_RE.fullmatch(network_id or ""):
            raise ValueError("Network ID do ZeroTier deve ter 16 caracteres hexadecimais.")
        cli = self._find_cli()
        if not cli:
            raise RuntimeError("ZeroTier não está instalado.")
        result = self._run([cli, "join", network_id])
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Não foi possível entrar na rede.").strip()
            raise RuntimeError(message)
        return {"ok": True, "output": (result.stdout or "OK").strip(), "status": self.status(network_id)}

    @staticmethod
    def _message_for(state: ZeroTierState) -> str:
        return {
            ZeroTierState.OFFLINE: "Serviço ZeroTier encontrado, porém offline.",
            ZeroTierState.ONLINE: "ZeroTier online; nenhuma rede selecionada foi confirmada.",
            ZeroTierState.TUNNELED: "ZeroTier conectado via relay/túnel. Pode haver maior latência.",
            ZeroTierState.ACCESS_DENIED: "Dispositivo ainda não autorizado na rede ZeroTier.",
            ZeroTierState.OK_PRIVATE: "ZeroTier conectado e rede privada autorizada.",
            ZeroTierState.NOT_INSTALLED: "ZeroTier não instalado.",
            ZeroTierState.UNKNOWN: "Não foi possível determinar o estado do ZeroTier.",
        }[state]
