"""Catálogo declarativo de serviços e execução assistida de planos permitidos."""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from pibic_lab_core.domain.models import (
    InstallationJob,
    InstallationPlan,
    ManifestStep,
    RemoteSystemInfo,
    ServiceManifest,
    utc_now_iso,
)
from pibic_lab_core.security.redaction import redact_text
from pibic_lab_core.util.commands import fixed, quote_args, validate_identifier, validate_packages


class CatalogRepository:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def list(self) -> list[ServiceManifest]:
        manifests: list[ServiceManifest] = []
        if not self.directory.exists():
            return manifests
        for path in sorted(self.directory.glob("*.y*ml")):
            manifests.append(self._load(path))
        return manifests

    def get(self, manifest_id: str) -> ServiceManifest:
        validate_identifier(manifest_id, "ID do manifest")
        for suffix in (".yaml", ".yml"):
            path = self.directory / f"{manifest_id}{suffix}"
            if path.exists():
                return self._load(path)
        raise ValueError(f"Manifest '{manifest_id}' não encontrado.")

    @staticmethod
    def _load(path: Path) -> ServiceManifest:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Manifest inválido: {path.name}")
        return ServiceManifest.model_validate(data)


class PackageInstaller:
    """Transforma manifests em jobs; não executa scripts arbitrários."""

    def __init__(self, ssh, detector, store, audit) -> None:
        self.ssh = ssh
        self.detector = detector
        self.store = store
        self.audit = audit
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pibic-installer")
        self._lock = threading.RLock()

    def build_plan(self, manifest: ServiceManifest, system: RemoteSystemInfo) -> InstallationPlan:
        os_id = (system.os_id or "").lower()
        os_version = system.os_version or ""
        compatible, reason = self._is_compatible(manifest, os_id, os_version)
        steps = manifest.install_plan.get(os_id, []) if compatible else []
        commands: list[str] = []
        for step in steps:
            commands.extend(self._preview_step(step))
        return InstallationPlan(
            manifest_id=manifest.id,
            manifest_name=manifest.name,
            compatible=compatible,
            os_id=os_id or None,
            os_version=os_version or None,
            requires_admin=manifest.requires_admin,
            steps=steps,
            commands_preview=commands,
            reason=reason,
        )

    @staticmethod
    def _is_compatible(manifest: ServiceManifest, os_id: str, version: str) -> tuple[bool, str | None]:
        supported = manifest.supported.get(os_id)
        if supported is None:
            return False, f"Sistema '{os_id or 'desconhecido'}' não está listado como compatível."
        if supported == "*":
            return True, None
        if version in supported:
            return True, None
        major = version.split(".", 1)[0] if version else ""
        if major and major in supported:
            return True, None
        return False, f"Versão {version or 'desconhecida'} não está listada no manifest."

    def _preview_step(self, step: ManifestStep) -> list[str]:
        if step.action == "apt_update":
            return ["apt-get update"]
        if step.action == "apt_install":
            validate_packages(step.packages)
            return [quote_args(["apt-get", "install", "-y", *step.packages])]
        if step.action == "apk_add":
            validate_packages(step.packages)
            return [quote_args(["apk", "add", *step.packages])]
        if step.action == "systemd_enable":
            service = validate_identifier(step.service or "", "serviço")
            return [quote_args(["systemctl", "enable", "--now", service])]
        if step.action == "openrc_enable":
            service = validate_identifier(step.service or "", "serviço")
            return [
                quote_args(["rc-update", "add", service, "default"]),
                quote_args(["rc-service", service, "start"]),
            ]
        if step.action == "run_fixed":
            return [fixed(step.command_id or "")]
        raise ValueError(f"Ação de manifest não permitida: {step.action}")

    def start_job(
        self,
        *,
        profile_id: int,
        actor: str,
        manifest: ServiceManifest,
        plan: InstallationPlan,
        elevation_password: str | None,
        confirmed: bool,
    ) -> InstallationJob:
        if not confirmed:
            raise PermissionError("A instalação exige confirmação explícita.")
        if not plan.compatible:
            raise ValueError(plan.reason or "Manifest incompatível.")
        job = InstallationJob(
            id=uuid.uuid4().hex,
            manifest_id=manifest.id,
            requested_by=actor,
            state="queued",
        )
        self.store.save_job(job)
        self.audit.log("catalog", "install_requested", actor, target=manifest.id, details={"job_id": job.id})
        self.executor.submit(
            self._execute_job,
            profile_id,
            actor,
            manifest,
            plan,
            elevation_password,
            job,
        )
        return job

    def _execute_job(
        self,
        profile_id: int,
        actor: str,
        manifest: ServiceManifest,
        plan: InstallationPlan,
        elevation_password: str | None,
        job: InstallationJob,
    ) -> None:
        job.state = "running"
        job.started_at = utc_now_iso()
        self.store.save_job(job)
        try:
            privilege = self.detector.privilege_info(profile_id)
            if manifest.requires_admin and not privilege["is_root"]:
                if not privilege["sudo"] and not privilege["doas"]:
                    raise PermissionError(
                        "A instalação exige root, sudo ou doas, mas nenhum elevador foi detectado."
                    )
                if not elevation_password:
                    raise PermissionError(
                        "Senha de elevação não informada para este job."
                    )

            for step in plan.steps:
                for command in self._preview_step(step):
                    job.output.append(f"$ {command}")
                    self.store.save_job(job)
                    result = self._run_privileged_if_needed(
                        profile_id,
                        command,
                        requires_admin=manifest.requires_admin,
                        privilege=privilege,
                        elevation_password=elevation_password,
                    )
                    stdout = redact_text((result["stdout"] or "").strip())
                    stderr = redact_text((result["stderr"] or "").strip())
                    if stdout:
                        job.output.extend(stdout.splitlines()[-80:])
                    if stderr:
                        job.output.extend([f"stderr: {line}" for line in stderr.splitlines()[-80:]])
                    job.exit_code = result["exit_status"]
                    self.store.save_job(job)
                    if result["exit_status"] != 0:
                        raise RuntimeError(f"Etapa falhou com código {result['exit_status']}.")

            if manifest.verify_command_id:
                verify = self.ssh.run_command(profile_id, fixed(manifest.verify_command_id), timeout=15)
                verify_text = ((verify["stdout"] or verify["stderr"] or "").strip())
                if verify["exit_status"] != 0 or not verify_text:
                    raise RuntimeError("A verificação pós-instalação não confirmou o serviço.")
                job.output.append("Verificação: " + redact_text(verify_text.splitlines()[0]))

            job.state = "success"
            job.exit_code = 0
            self.audit.log("catalog", "install_finished", actor, target=manifest.id, details={"job_id": job.id})
        except Exception as exc:
            job.state = "failed"
            job.error = redact_text(str(exc))
            self.audit.log(
                "catalog",
                "install_failed",
                actor,
                target=manifest.id,
                outcome="error",
                details={"job_id": job.id, "error": job.error},
            )
        finally:
            # A referência local à senha deixa de ser usada ao final do job; ela nunca é persistida.
            elevation_password = None
            job.finished_at = utc_now_iso()
            self.store.save_job(job)

    def _run_privileged_if_needed(
        self,
        profile_id: int,
        command: str,
        *,
        requires_admin: bool,
        privilege: dict[str, Any],
        elevation_password: str | None,
    ) -> dict[str, Any]:
        if not requires_admin or privilege["is_root"]:
            return self.ssh.run_command(profile_id, command, timeout=180)
        stdin_data = ((elevation_password or "") + "\n").encode("utf-8")

        if privilege.get("sudo"):
            sudo_command = f"sudo -S -p '' -- {command}"
            return self.ssh.run_command_with_stdin(
                profile_id,
                sudo_command,
                stdin_data,
                timeout=180,
            )

        if privilege.get("doas"):
            doas_command = f"doas {command}"
            return self.ssh.run_command_with_pty_stdin(
                profile_id,
                doas_command,
                stdin_data,
                timeout=180,
            )

        raise PermissionError("Nenhum mecanismo de elevação disponível.")
