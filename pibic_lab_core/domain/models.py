"""Modelos de domínio do PIBIC LAB.

Este módulo não depende do Vela. A ideia é manter o núcleo reutilizável caso a
camada visual seja trocada no futuro.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Role(str, Enum):
    STUDENT = "student"
    ADMIN = "admin"
    ADVISOR = "advisor"


class AuthMethod(str, Enum):
    AGENT = "agent"
    KEY = "key"
    PASSWORD = "password"


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ZeroTierState(str, Enum):
    NOT_INSTALLED = "not_installed"
    OFFLINE = "offline"
    ONLINE = "online"
    TUNNELED = "tunneled"
    ACCESS_DENIED = "access_denied"
    OK_PRIVATE = "ok_private"
    UNKNOWN = "unknown"


class Environment(BaseModel):
    id: int | None = None
    name: str = "Laboratório PIBIC / UNIR"
    gateway_host: str = "10.57.144.217"
    ssh_port: int = 22
    proxmox_internal_host: str = "10.99.0.59"
    proxmox_port: int = 8006
    zerotier_network_id: str = ""
    enabled: bool = True

    @field_validator("ssh_port", "proxmox_port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("Porta inválida")
        return value


class UserProfile(BaseModel):
    id: int | None = None
    display_name: str = "Meu perfil"
    role: Role = Role.STUDENT
    ssh_username: str = ""
    assigned_vmids: list[int] = Field(default_factory=list)
    can_proxmox_power: bool = False
    can_install_services: bool = False
    created_at: str = Field(default_factory=utc_now_iso)


class SSHConnectionConfig(BaseModel):
    environment_id: int = 1
    host: str
    port: int = 22
    username: str
    auth_method: AuthMethod = AuthMethod.AGENT
    key_path: str | None = None
    save_password: bool = False

    @field_validator("host", "username")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Campo obrigatório")
        return value


class HostKeyInfo(BaseModel):
    host: str
    port: int
    algorithm: str
    fingerprint_sha256: str
    public_key: str
    trusted: bool = False
    changed: bool = False


class RemoteSystemInfo(BaseModel):
    hostname: str | None = None
    os_name: str | None = None
    os_id: str | None = None
    os_version: str | None = None
    kernel: str | None = None
    architecture: str | None = None
    cpu_model: str | None = None
    cpu_count: int | None = None
    ram_total: int | None = None
    ram_used: int | None = None
    disk_total: int | None = None
    disk_used: int | None = None
    disk_free: int | None = None
    ip_addresses: list[str] = Field(default_factory=list)
    uptime_seconds: int | None = None


class DetectedService(BaseModel):
    id: str
    name: str
    installed: bool
    version: str | None = None
    status: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    detected_at: str = Field(default_factory=utc_now_iso)


class DockerContainer(BaseModel):
    id: str
    name: str
    image: str
    state: str
    status: str | None = None
    ports: str | None = None
    compose_project: str | None = None


class ProxmoxVM(BaseModel):
    vmid: int
    name: str
    node: str | None = None
    status: str | None = None
    cpu: float | None = None
    maxcpu: float | None = None
    mem: int | None = None
    maxmem: int | None = None
    disk: int | None = None
    maxdisk: int | None = None
    uptime: int | None = None
    vm_type: str | None = None


class ManifestStep(BaseModel):
    action: Literal[
        "apt_update",
        "apt_install",
        "apk_add",
        "systemd_enable",
        "openrc_enable",
        "run_fixed",
    ]
    packages: list[str] = Field(default_factory=list)
    service: str | None = None
    command_id: str | None = None
    description: str = ""


class ServiceManifest(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str
    manifest_version: int = 1
    supported: dict[str, list[str] | Literal["*"]] = Field(default_factory=dict)
    detect_command_id: str
    verify_command_id: str | None = None
    install_plan: dict[str, list[ManifestStep]] = Field(default_factory=dict)
    documentation: str | None = None
    requires_admin: bool = False
    icon: str = "package"


class InstallationPlan(BaseModel):
    manifest_id: str
    manifest_name: str
    compatible: bool
    os_id: str | None = None
    os_version: str | None = None
    requires_admin: bool = False
    steps: list[ManifestStep] = Field(default_factory=list)
    commands_preview: list[str] = Field(default_factory=list)
    reason: str | None = None


class InstallationJob(BaseModel):
    id: str
    manifest_id: str
    requested_by: str
    state: Literal["queued", "running", "success", "failed", "cancelled"] = "queued"
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    output: list[str] = Field(default_factory=list)
    error: str | None = None


class AuditEvent(BaseModel):
    id: str
    timestamp: str = Field(default_factory=utc_now_iso)
    category: str
    action: str
    actor: str
    target: str | None = None
    outcome: str = "ok"
    details: dict[str, Any] = Field(default_factory=dict)


class AppSettings(BaseModel):
    theme: Literal["dark", "light"] = "dark"
    poll_interval_ms: int = 120
    terminal_scrollback: int = 5000
    verify_proxmox_tls: bool = True
    proxmox_ca_path: str = ""
    catalog_url: str = ""
    allow_unsafe_proxmox_tls: bool = False

    @field_validator("poll_interval_ms")
    @classmethod
    def safe_poll_interval(cls, value: int) -> int:
        return max(80, min(value, 1000))
