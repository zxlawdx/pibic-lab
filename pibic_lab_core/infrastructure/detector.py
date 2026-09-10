"""Detecção somente leitura do sistema remoto."""
from __future__ import annotations

import re
from typing import Any

from pibic_lab_core.domain.models import DetectedService, RemoteSystemInfo
from pibic_lab_core.util.commands import fixed


class ServiceDetector:
    SERVICE_COMMANDS = {
        "git": ("Git", "git"),
        "python": ("Python", "python"),
        "node": ("Node.js", "node"),
        "docker": ("Docker", "docker"),
        "compose": ("Docker Compose", "compose"),
        "postgresql": ("PostgreSQL", "postgresql"),
        "nginx": ("Nginx", "nginx"),
        "apache": ("Apache", "apache"),
        "ssh": ("SSH Server", "ssh_server"),
    }

    def __init__(self, ssh) -> None:
        self.ssh = ssh

    def system_info(self, profile_id: int) -> RemoteSystemInfo:
        outputs: dict[str, str] = {}
        for key in (
            "os_release",
            "kernel",
            "hostname",
            "arch",
            "cpu_count",
            "cpu_model",
            "meminfo",
            "disk_root",
            "ip_addresses",
            "uptime",
        ):
            result = self.ssh.run_command(profile_id, fixed(key), timeout=8)
            outputs[key] = (result["stdout"] or result["stderr"] or "").strip()

        os_release = self._parse_os_release(outputs["os_release"])
        mem = self._parse_meminfo(outputs["meminfo"])
        disk = self._parse_disk(outputs["disk_root"])
        return RemoteSystemInfo(
            hostname=outputs["hostname"] or None,
            os_name=os_release.get("PRETTY_NAME") or os_release.get("NAME"),
            os_id=os_release.get("ID"),
            os_version=os_release.get("VERSION_ID"),
            kernel=outputs["kernel"] or None,
            architecture=outputs["arch"] or None,
            cpu_model=outputs["cpu_model"] or None,
            cpu_count=self._int_or_none(outputs["cpu_count"]),
            ram_total=mem.get("MemTotal"),
            ram_used=self._ram_used(mem),
            disk_total=disk.get("total"),
            disk_used=disk.get("used"),
            disk_free=disk.get("free"),
            ip_addresses=[item for item in outputs["ip_addresses"].split() if item],
            uptime_seconds=self._int_or_none(outputs["uptime"]),
        )

    def detect_services(self, profile_id: int) -> list[DetectedService]:
        services: list[DetectedService] = []
        for service_id, (name, command_id) in self.SERVICE_COMMANDS.items():
            result = self.ssh.run_command(profile_id, fixed(command_id), timeout=8)
            text = (result["stdout"] or result["stderr"] or "").strip()
            services.append(
                DetectedService(
                    id=service_id,
                    name=name,
                    installed=bool(text),
                    version=self._version_from_output(text) if text else None,
                    status="detectado" if text else "não encontrado",
                )
            )

        # pgVector não deve ser inferido por pacote/arquivo. Sem uma conexão DB autorizada,
        # o estado permanece deliberadamente não confirmado.
        services.append(
            DetectedService(
                id="pgvector",
                name="pgVector",
                installed=False,
                version=None,
                status="não confirmado",
                details={"reason": "Requer consulta a um banco PostgreSQL autorizado."},
            )
        )
        return services

    def privilege_info(self, profile_id: int) -> dict[str, Any]:
        uid = self.ssh.run_command(profile_id, fixed("id_u"), timeout=5)["stdout"].strip()
        sudo = self.ssh.run_command(profile_id, fixed("sudo_check"), timeout=5)["stdout"].strip() == "yes"
        doas = self.ssh.run_command(profile_id, fixed("doas_check"), timeout=5)["stdout"].strip() == "yes"
        return {"is_root": uid == "0", "sudo": sudo, "doas": doas}

    @staticmethod
    def _parse_os_release(text: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in text.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            result[key] = value.strip().strip('"').strip("'")
        return result

    @staticmethod
    def _parse_meminfo(text: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for line in text.splitlines():
            match = re.match(r"^(\w+):\s+(\d+)\s+kB", line)
            if match:
                result[match.group(1)] = int(match.group(2)) * 1024
        return result

    @staticmethod
    def _ram_used(mem: dict[str, int]) -> int | None:
        total = mem.get("MemTotal")
        available = mem.get("MemAvailable")
        if total is None:
            return None
        if available is not None:
            return max(0, total - available)
        free = sum(mem.get(k, 0) for k in ("MemFree", "Buffers", "Cached"))
        return max(0, total - free)

    @staticmethod
    def _parse_disk(text: str) -> dict[str, int]:
        parts = text.split()
        if len(parts) < 4:
            return {}
        try:
            return {"total": int(parts[1]), "used": int(parts[2]), "free": int(parts[3])}
        except ValueError:
            return {}

    @staticmethod
    def _int_or_none(value: str) -> int | None:
        try:
            return int(value.strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _version_from_output(text: str) -> str:
        first = text.splitlines()[0].strip()
        match = re.search(r"(?:version\s+|v)([0-9][A-Za-z0-9._+-]*)", first, re.IGNORECASE)
        return match.group(1) if match else first[:120]
