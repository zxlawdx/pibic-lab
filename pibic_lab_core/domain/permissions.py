"""Autorização explícita por perfil."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Role, UserProfile


@dataclass(frozen=True)
class PermissionSet:
    terminal: bool
    proxmox_read: bool
    proxmox_power: bool
    services_read: bool
    services_install: bool
    docker_read: bool
    docker_power: bool
    audit_read: bool


def permissions_for(profile: UserProfile) -> PermissionSet:
    if profile.role == Role.ADMIN:
        return PermissionSet(True, True, True, True, True, True, True, True)

    if profile.role == Role.ADVISOR:
        return PermissionSet(
            terminal=True,
            proxmox_read=True,
            proxmox_power=profile.can_proxmox_power,
            services_read=True,
            services_install=profile.can_install_services,
            docker_read=True,
            docker_power=False,
            audit_read=True,
        )

    return PermissionSet(
        terminal=True,
        proxmox_read=True,
        proxmox_power=profile.can_proxmox_power,
        services_read=True,
        services_install=profile.can_install_services,
        docker_read=True,
        docker_power=False,
        audit_read=False,
    )


def assert_vm_allowed(profile: UserProfile, vmid: int) -> None:
    if profile.role == Role.ADMIN:
        return
    if vmid not in profile.assigned_vmids:
        raise PermissionError(f"VM {vmid} não está atribuída a este perfil.")
