"""Casos de uso expostos à camada Vela/API."""
from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pibic_lab_core.audit.service import AuditService
from pibic_lab_core.domain.models import (
    AppSettings,
    AuthMethod,
    Environment,
    HostKeyInfo,
    Role,
    SSHConnectionConfig,
    UserProfile,
)
from pibic_lab_core.domain.permissions import permissions_for
from pibic_lab_core.infrastructure.catalog import CatalogRepository, PackageInstaller
from pibic_lab_core.infrastructure.credential_store import CredentialStore
from pibic_lab_core.infrastructure.detector import ServiceDetector
from pibic_lab_core.infrastructure.diagnostics import DiagnosticsExporter
from pibic_lab_core.infrastructure.docker_service import DockerService
from pibic_lab_core.infrastructure.proxmox_service import ProxmoxService
from pibic_lab_core.infrastructure.sqlite_store import SQLiteStore
from pibic_lab_core.infrastructure.ssh_service import SSHSessionManager
from pibic_lab_core.infrastructure.zerotier import ZeroTierAdapter
from pibic_lab_core.util.paths import bundled_catalog_dir, database_path, known_hosts_path, log_dir


class AppFacade:
    VERSION = "0.1.2"

    def __init__(self) -> None:
        self.store = SQLiteStore(database_path())
        self.credentials = CredentialStore()
        self.audit = AuditService(log_dir())
        self.zerotier = ZeroTierAdapter()
        self.ssh = SSHSessionManager(known_hosts_path())
        self.detector = ServiceDetector(self.ssh)
        self.docker = DockerService(self.ssh)
        self.proxmox = ProxmoxService(self.ssh, self.audit)
        self.catalog = CatalogRepository(bundled_catalog_dir())
        self.installer = PackageInstaller(self.ssh, self.detector, self.store, self.audit)
        self.diagnostics = DiagnosticsExporter(self.store, self.audit)

    # Bootstrap/config --------------------------------------------------------------
    def bootstrap(self, profile_id: int | None = None, environment_id: int | None = None) -> dict[str, Any]:
        profiles = self.store.list_profiles()
        environments = self.store.list_environments()
        if not profiles:
            raise RuntimeError("Nenhum perfil disponível.")
        if not environments:
            raise RuntimeError("Nenhum ambiente disponível.")
        profile = self._profile(profile_id or profiles[0].id or 1)
        env = self._environment(environment_id or environments[0].id or 1)
        return {
            "app": {"name": "PIBIC LAB", "version": self.VERSION},
            "profiles": [self._profile_public(p) for p in profiles],
            "environments": [e.model_dump() for e in environments],
            "profile": self._profile_public(profile),
            "environment": env.model_dump(),
            "ssh_preferences": self.store.get_ssh_preferences(profile.id or 0),
            "proxmox_preferences": self._proxmox_public(profile.id or 0),
            "permissions": permissions_for(profile).__dict__,
            "settings": self.store.get_settings().model_dump(),
            "ssh": self.ssh.status(profile.id or 0),
            "zerotier": self.zerotier.status(env.zerotier_network_id),
        }

    def save_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        profile = UserProfile.model_validate(data)
        saved = self.store.save_profile(profile)
        self.audit.log("settings", "profile_saved", saved.display_name, target=str(saved.id))
        return self._profile_public(saved)

    def save_connection_preferences(self, profile_id: int, data: dict[str, Any]) -> dict[str, Any]:
        profile = self._profile(profile_id)
        auth_method = AuthMethod(data.get("auth_method", "agent"))
        key_path = str(data.get("key_path") or "").strip()
        save_password = bool(data.get("save_password", False))
        self.store.save_ssh_preferences(profile.id or 0, auth_method.value, key_path, save_password)
        return self.store.get_ssh_preferences(profile.id or 0)

    def save_environment(self, data: dict[str, Any]) -> dict[str, Any]:
        environment = Environment.model_validate(data)
        return self.store.save_environment(environment).model_dump()

    def settings(self) -> dict[str, Any]:
        return self.store.get_settings().model_dump()

    def save_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        settings = AppSettings.model_validate(data)
        return self.store.save_settings(settings).model_dump()

    # Connectivity ------------------------------------------------------------------
    def connectivity(self, environment_id: int) -> dict[str, Any]:
        env = self._environment(environment_id)
        zt = self.zerotier.status(env.zerotier_network_id)
        gateway = self._tcp_check(env.gateway_host, env.ssh_port)
        return {"zerotier": zt, "gateway": gateway}

    def zerotier_join(self, environment_id: int, network_id: str) -> dict[str, Any]:
        env = self._environment(environment_id)
        env.zerotier_network_id = network_id.strip()
        self.store.save_environment(env)
        result = self.zerotier.join(env.zerotier_network_id)
        self.audit.log("connectivity", "zerotier_join", "local-user", target=network_id)
        return result

    @staticmethod
    def _tcp_check(host: str, port: int) -> dict[str, Any]:
        try:
            with socket.create_connection((host, port), timeout=2.5):
                return {"available": True, "host": host, "port": port}
        except OSError as exc:
            return {"available": False, "host": host, "port": port, "error": str(exc)}

    # SSH ---------------------------------------------------------------------------
    def ssh_probe(self, environment_id: int) -> dict[str, Any]:
        env = self._environment(environment_id)
        info = self.ssh.probe_host_key(env.gateway_host, env.ssh_port)
        return info.model_dump()

    def ssh_trust(self, data: dict[str, Any], profile_id: int) -> dict[str, Any]:
        info = HostKeyInfo.model_validate(data)
        envs = self.store.list_environments()
        allowed = any(e.gateway_host == info.host and e.ssh_port == info.port for e in envs)
        if not allowed:
            raise PermissionError("Host key não corresponde a um ambiente cadastrado.")
        self.ssh.trust_host_key(info)
        profile = self._profile(profile_id)
        self.audit.log(
            "ssh",
            "host_key_trusted",
            profile.display_name,
            target=f"{info.host}:{info.port}",
            details={"fingerprint": info.fingerprint_sha256, "algorithm": info.algorithm},
        )
        return {"ok": True}

    def ssh_connect(self, profile_id: int, environment_id: int, data: dict[str, Any]) -> dict[str, Any]:
        profile = self._profile(profile_id)
        env = self._environment(environment_id)
        prefs = self.store.get_ssh_preferences(profile_id)
        username = str(data.get("username") or profile.ssh_username or "").strip()
        if not username:
            raise ValueError("Informe o usuário SSH.")

        auth_method = AuthMethod(data.get("auth_method") or prefs["auth_method"])
        key_path = str(data.get("key_path") or prefs.get("key_path") or "").strip() or None
        save_password = bool(data.get("save_password", prefs.get("save_password", False)))
        config = SSHConnectionConfig(
            environment_id=environment_id,
            host=env.gateway_host,
            port=env.ssh_port,
            username=username,
            auth_method=auth_method,
            key_path=key_path,
            save_password=save_password,
        )

        # Revalida a host key imediatamente antes de enviar qualquer credencial.
        key_info = self.ssh.probe_host_key(env.gateway_host, env.ssh_port)
        if key_info.changed:
            raise PermissionError(
                f"A host key mudou. Conexão bloqueada. Fingerprint atual: {key_info.fingerprint_sha256}"
            )
        if not key_info.trusted:
            raise PermissionError(
                f"Host key ainda não foi confirmada. Fingerprint: {key_info.fingerprint_sha256}"
            )

        password = str(data.get("password") or "") or None
        if auth_method == AuthMethod.PASSWORD:
            if not password:
                password = self.credentials.get_secret("ssh_password", profile_id)
            if save_password and password:
                self.credentials.set_secret("ssh_password", profile_id, password)
            elif not save_password:
                self.credentials.delete_secret("ssh_password", profile_id)

        key_passphrase = str(data.get("key_passphrase") or "") or None
        if not key_passphrase:
            key_passphrase = self.credentials.get_secret("ssh_key_passphrase", profile_id)
        if bool(data.get("save_key_passphrase")) and key_passphrase:
            self.credentials.set_secret("ssh_key_passphrase", profile_id, key_passphrase)

        # Atualiza apenas metadados não secretos.
        profile.ssh_username = username
        self.store.save_profile(profile)
        self.store.save_ssh_preferences(profile_id, auth_method.value, key_path or "", save_password)

        result = self.ssh.connect(
            profile_id,
            config,
            password=password,
            key_passphrase=key_passphrase,
        )
        password = None
        key_passphrase = None
        self.audit.log(
            "ssh",
            "connect",
            profile.display_name,
            target=f"{env.gateway_host}:{env.ssh_port}",
            details={"auth_method": auth_method.value, "username": username},
        )
        return result

    def ssh_disconnect(self, profile_id: int) -> dict[str, Any]:
        profile = self._profile(profile_id)
        self.ssh.disconnect(profile_id)
        self.audit.log("ssh", "disconnect", profile.display_name)
        return {"ok": True}

    def ssh_status(self, profile_id: int) -> dict[str, Any]:
        return self.ssh.status(profile_id)

    # Terminal ----------------------------------------------------------------------
    def terminal_open(self, profile_id: int, cols: int, rows: int) -> dict[str, Any]:
        profile = self._profile(profile_id)
        if not permissions_for(profile).terminal:
            raise PermissionError("Perfil sem acesso ao terminal.")
        result = self.ssh.open_terminal(profile_id, cols, rows)
        self.audit.log("terminal", "open", profile.display_name, details={"session_id": result["session_id"]})
        return result

    def terminal_input(self, profile_id: int, session_id: str, data_b64: str) -> dict[str, Any]:
        self.ssh.terminal_input(profile_id, session_id, data_b64)
        return {"ok": True}

    def terminal_resize(self, profile_id: int, session_id: str, cols: int, rows: int) -> dict[str, Any]:
        self.ssh.terminal_resize(profile_id, session_id, cols, rows)
        return {"ok": True}

    def terminal_poll(self, profile_id: int, session_id: str) -> dict[str, Any]:
        return self.ssh.terminal_poll(profile_id, session_id)

    def terminal_close(self, profile_id: int, session_id: str) -> dict[str, Any]:
        profile = self._profile(profile_id)
        self.ssh.close_terminal(profile_id, session_id)
        self.audit.log("terminal", "close", profile.display_name, details={"session_id": session_id})
        return {"ok": True}

    # Dashboard/services ------------------------------------------------------------
    def dashboard(self, profile_id: int) -> dict[str, Any]:
        profile = self._profile(profile_id)
        if not self.ssh.is_connected(profile_id):
            return {"connected": False, "profile": self._profile_public(profile)}
        system = self.detector.system_info(profile_id)
        services = self.detector.detect_services(profile_id)
        for service in services:
            self.store.save_detected_service(profile_id, service.id, service.model_dump_json())
        return {
            "connected": True,
            "profile": self._profile_public(profile),
            "ssh": self.ssh.status(profile_id),
            "system": system.model_dump(),
            "services": [s.model_dump() for s in services],
            "privilege": self.detector.privilege_info(profile_id),
        }

    def detect_services(self, profile_id: int) -> list[dict[str, Any]]:
        profile = self._profile(profile_id)
        if not permissions_for(profile).services_read:
            raise PermissionError("Perfil sem permissão para detectar serviços.")
        services = self.detector.detect_services(profile_id)
        for service in services:
            self.store.save_detected_service(profile_id, service.id, service.model_dump_json())
        return [s.model_dump() for s in services]

    def catalog_list(self) -> list[dict[str, Any]]:
        return [m.model_dump() for m in self.catalog.list()]

    def catalog_plan(self, profile_id: int, manifest_id: str) -> dict[str, Any]:
        profile = self._profile(profile_id)
        if not permissions_for(profile).services_read:
            raise PermissionError("Perfil sem permissão para consultar catálogo.")
        system = self.detector.system_info(profile_id)
        manifest = self.catalog.get(manifest_id)
        return self.installer.build_plan(manifest, system).model_dump()

    def catalog_install(self, profile_id: int, manifest_id: str, data: dict[str, Any]) -> dict[str, Any]:
        profile = self._profile(profile_id)
        if not permissions_for(profile).services_install:
            raise PermissionError("Este perfil não possui permissão local para instalação assistida.")
        system = self.detector.system_info(profile_id)
        manifest = self.catalog.get(manifest_id)
        plan = self.installer.build_plan(manifest, system)
        job = self.installer.start_job(
            profile_id=profile_id,
            actor=profile.display_name,
            manifest=manifest,
            plan=plan,
            elevation_password=str(data.get("elevation_password") or "") or None,
            confirmed=bool(data.get("confirmed")),
        )
        return job.model_dump()

    def jobs(self) -> list[dict[str, Any]]:
        return [job.model_dump() for job in self.store.list_jobs()]

    # Docker ------------------------------------------------------------------------
    def docker_list(self, profile_id: int) -> dict[str, Any]:
        profile = self._profile(profile_id)
        if not permissions_for(profile).docker_read:
            raise PermissionError("Perfil sem permissão para consultar Docker.")
        return self.docker.list_containers(profile_id)

    def docker_action(self, profile_id: int, container_id: str, action: str, confirmed: bool) -> dict[str, Any]:
        profile = self._profile(profile_id)
        if not permissions_for(profile).docker_power:
            raise PermissionError("Ações Docker são restritas ao perfil administrativo neste MVP.")
        if not confirmed:
            raise PermissionError("A ação Docker exige confirmação explícita.")
        result = self.docker.action(profile_id, container_id, action)
        self.audit.log("docker", action, profile.display_name, target=container_id, outcome="ok" if result["ok"] else "error")
        return result

    # Proxmox -----------------------------------------------------------------------
    def save_proxmox_credentials(self, profile_id: int, api_user: str, token_name: str, token_secret: str) -> dict[str, Any]:
        profile = self._profile(profile_id)
        self.store.save_proxmox_preferences(profile_id, api_user.strip(), token_name.strip())
        if token_secret:
            self.credentials.set_secret("proxmox_token", profile_id, token_secret)
        self.audit.log("settings", "proxmox_credentials_saved", profile.display_name)
        return self._proxmox_public(profile_id)

    def delete_proxmox_secret(self, profile_id: int) -> dict[str, Any]:
        self.credentials.delete_secret("proxmox_token", profile_id)
        return self._proxmox_public(profile_id)

    def proxmox_list(self, profile_id: int, environment_id: int) -> list[dict[str, Any]]:
        profile = self._profile(profile_id)
        env = self._environment(environment_id)
        prefs = self.store.get_proxmox_preferences(profile_id)
        secret = self.credentials.get_secret("proxmox_token", profile_id) or ""
        vms = self.proxmox.list_vms(
            profile=profile,
            environment=env,
            api_user=prefs.get("api_user", ""),
            token_name=prefs.get("token_name", ""),
            token_secret=secret,
            settings=self.store.get_settings(),
        )
        return [vm.model_dump() for vm in vms]

    def proxmox_creation_options(
        self,
        profile_id: int,
        environment_id: int,
    ) -> dict[str, Any]:

        profile = self._profile(
            profile_id
        )

        env = self._environment(
            environment_id
        )

        prefs = self.store.get_proxmox_preferences(
            profile_id
        )

        secret = (
            self.credentials.get_secret(
                "proxmox_token",
                profile_id,
            )
            or ""
        )

        return self.proxmox.creation_options(
            profile=profile,
            environment=env,
            api_user=prefs.get(
                "api_user",
                "",
            ),
            token_name=prefs.get(
                "token_name",
                "",
            ),
            token_secret=secret,
            settings=self.store.get_settings(),
        )

    def proxmox_task_cancel(self, profile_id: int, environment_id: int, data: dict[str, Any]) -> dict[str, Any]:
        profile, env, prefs, secret, settings = self._proxmox_context(profile_id, environment_id)
        return self.proxmox.cancel_task(
            profile=profile,
            environment=env,
            api_user=prefs.get("api_user", ""),
            token_name=prefs.get("token_name", ""),
            token_secret=secret,
            settings=settings,
            node=str(data.get("node") or ""),
            upid=str(data.get("upid") or ""),
        )

    def proxmox_create_vm(
        self,
        profile_id: int,
        environment_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:

        profile = self._profile(
            profile_id
        )

        env = self._environment(
            environment_id
        )

        prefs = self.store.get_proxmox_preferences(
            profile_id
        )

        secret = (
            self.credentials.get_secret(
                "proxmox_token",
                profile_id,
            )
            or ""
        )

        return self.proxmox.create_vm(
            profile=profile,
            environment=env,
            api_user=prefs.get(
                "api_user",
                "",
            ),
            token_name=prefs.get(
                "token_name",
                "",
            ),
            token_secret=secret,
            settings=self.store.get_settings(),
            data=data,
        )

    def _proxmox_context(self, profile_id: int, environment_id: int):
        profile = self._profile(profile_id)
        env = self._environment(environment_id)
        prefs = self.store.get_proxmox_preferences(profile_id)
        secret = self.credentials.get_secret("proxmox_token", profile_id) or ""
        settings = self.store.get_settings()
        return profile, env, prefs, secret, settings

    def proxmox_install_options(self, profile_id: int, environment_id: int) -> dict[str, Any]:
        profile, env, prefs, secret, settings = self._proxmox_context(profile_id, environment_id)
        return self.proxmox.installer_options(
            profile=profile, environment=env,
            api_user=prefs.get("api_user", ""), token_name=prefs.get("token_name", ""),
            token_secret=secret, settings=settings,
        )

    def proxmox_node_options(self, profile_id: int, environment_id: int, node: str) -> dict[str, Any]:
        profile, env, prefs, secret, settings = self._proxmox_context(profile_id, environment_id)
        return self.proxmox.node_install_options(
            profile=profile, environment=env,
            api_user=prefs.get("api_user", ""), token_name=prefs.get("token_name", ""),
            token_secret=secret, settings=settings, node=node,
        )

    def proxmox_iso_query(self, profile_id: int, environment_id: int, data: dict[str, Any]) -> dict[str, Any]:
        profile, env, prefs, secret, settings = self._proxmox_context(profile_id, environment_id)
        return self.proxmox.query_iso_url(
            profile=profile, environment=env,
            api_user=prefs.get("api_user", ""), token_name=prefs.get("token_name", ""),
            token_secret=secret, settings=settings,
            node=str(data.get("node") or ""), url=str(data.get("url") or ""),
            verify_certificates=bool(data.get("verify_certificates", True)),
        )

    def proxmox_iso_download(self, profile_id: int, environment_id: int, data: dict[str, Any]) -> dict[str, Any]:
        profile, env, prefs, secret, settings = self._proxmox_context(profile_id, environment_id)
        return self.proxmox.download_iso(
            profile=profile, environment=env,
            api_user=prefs.get("api_user", ""), token_name=prefs.get("token_name", ""),
            token_secret=secret, settings=settings, data=data,
        )

    def proxmox_task_status(self, profile_id: int, environment_id: int, data: dict[str, Any]) -> dict[str, Any]:
        profile, env, prefs, secret, settings = self._proxmox_context(profile_id, environment_id)
        return self.proxmox.task_status(
            profile=profile, environment=env,
            api_user=prefs.get("api_user", ""), token_name=prefs.get("token_name", ""),
            token_secret=secret, settings=settings,
            node=str(data.get("node") or ""), upid=str(data.get("upid") or ""),
        )

    def proxmox_clone_vm(self, profile_id: int, environment_id: int, data: dict[str, Any]) -> dict[str, Any]:
        profile, env, prefs, secret, settings = self._proxmox_context(profile_id, environment_id)
        return self.proxmox.clone_vm(
            profile=profile, environment=env,
            api_user=prefs.get("api_user", ""), token_name=prefs.get("token_name", ""),
            token_secret=secret, settings=settings, data=data,
        )

    def proxmox_web_open(self, profile_id: int, environment_id: int) -> dict[str, Any]:
        profile, env, prefs, secret, settings = self._proxmox_context(profile_id, environment_id)
        return self.proxmox.open_web_forward(
            profile=profile, environment=env,
            api_user=prefs.get("api_user", ""), token_name=prefs.get("token_name", ""),
            token_secret=secret, settings=settings,
        )

    def proxmox_action(self, profile_id: int, environment_id: int, data: dict[str, Any]) -> dict[str, Any]:
        profile = self._profile(profile_id)
        env = self._environment(environment_id)
        prefs = self.store.get_proxmox_preferences(profile_id)
        secret = self.credentials.get_secret("proxmox_token", profile_id) or ""
        return self.proxmox.power_action(
            profile=profile,
            environment=env,
            api_user=prefs.get("api_user", ""),
            token_name=prefs.get("token_name", ""),
            token_secret=secret,
            settings=self.store.get_settings(),
            vmid=int(data.get("vmid")),
            node=str(data.get("node") or ""),
            vm_type=str(data.get("vm_type") or "qemu"),
            action=str(data.get("action") or ""),
            confirmed=bool(data.get("confirmed")),
        )

    # Logs/diagnostics ---------------------------------------------------------------
    def logs(self, profile_id: int, limit: int = 200) -> list[dict[str, Any]]:
        profile = self._profile(profile_id)
        events = self.audit.recent(limit)
        if permissions_for(profile).audit_read:
            return events
        return [event for event in events if event.get("actor") == profile.display_name]

    def export_diagnostics(self, profile_id: int, environment_id: int) -> dict[str, Any]:
        runtime = {
            "profile_id": profile_id,
            "environment_id": environment_id,
            "ssh": self.ssh.status(profile_id),
            "connectivity": self.connectivity(environment_id),
        }
        path = self.diagnostics.export(runtime)
        return {"ok": True, "path": str(path)}

    # Helpers -----------------------------------------------------------------------
    def _profile(self, profile_id: int) -> UserProfile:
        return self.store.get_profile(int(profile_id))

    def _environment(self, environment_id: int) -> Environment:
        return self.store.get_environment(int(environment_id))

    def _profile_public(self, profile: UserProfile) -> dict[str, Any]:
        data = profile.model_dump()
        data["permissions"] = permissions_for(profile).__dict__
        data["has_saved_ssh_password"] = self.credentials.has_secret("ssh_password", profile.id or 0)
        data["has_saved_key_passphrase"] = self.credentials.has_secret("ssh_key_passphrase", profile.id or 0)
        return data

    def _proxmox_public(self, profile_id: int) -> dict[str, Any]:
        data = self.store.get_proxmox_preferences(profile_id)
        data["has_token_secret"] = self.credentials.has_secret("proxmox_token", profile_id)
        return data
