"""Inspeção e ações Docker via CLI remota sobre SSH."""
from __future__ import annotations

import json
from typing import Any

from pibic_lab_core.domain.models import DockerContainer
from pibic_lab_core.util.commands import fixed, quote_args, validate_identifier


class DockerService:
    def __init__(self, ssh) -> None:
        self.ssh = ssh

    def list_containers(self, profile_id: int) -> dict[str, Any]:
        result = self.ssh.run_command(profile_id, fixed("docker_ps_json"), timeout=12)
        stderr = (result["stderr"] or "").strip()
        lines = [line.strip() for line in (result["stdout"] or "").splitlines() if line.strip()]
        containers: list[DockerContainer] = []
        parse_errors = 0
        for line in lines:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            containers.append(
                DockerContainer(
                    id=str(item.get("ID") or item.get("Id") or ""),
                    name=str(item.get("Names") or item.get("Name") or ""),
                    image=str(item.get("Image") or ""),
                    state=str(item.get("State") or "unknown"),
                    status=str(item.get("Status") or ""),
                    ports=str(item.get("Ports") or ""),
                    compose_project=str(item.get("Label", "")) or None,
                )
            )
        return {
            "available": result["exit_status"] == 0 and (bool(lines) or not stderr),
            "containers": [item.model_dump() for item in containers],
            "stderr": stderr,
            "parse_errors": parse_errors,
        }

    def action(self, profile_id: int, container_id: str, action: str) -> dict[str, Any]:
        validate_identifier(container_id, "ID/nome do container")
        if action not in {"start", "stop", "restart"}:
            raise ValueError("Ação Docker não permitida.")
        command = quote_args(["docker", action, container_id])
        result = self.ssh.run_command(profile_id, command, timeout=30)
        return {
            "ok": result["exit_status"] == 0,
            "stdout": result["stdout"].strip(),
            "stderr": result["stderr"].strip(),
            "exit_status": result["exit_status"],
        }
