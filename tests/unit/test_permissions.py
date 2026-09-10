from pibic_lab_core.domain.models import Role, UserProfile
from pibic_lab_core.domain.permissions import assert_vm_allowed, permissions_for


def test_student_permissions_are_conservative():
    profile = UserProfile(role=Role.STUDENT, assigned_vmids=[101])
    perms = permissions_for(profile)
    assert perms.terminal is True
    assert perms.proxmox_read is True
    assert perms.proxmox_power is False
    assert perms.services_install is False
    assert perms.docker_power is False


def test_assigned_vm_is_enforced_for_non_admin():
    profile = UserProfile(role=Role.STUDENT, assigned_vmids=[101])
    assert_vm_allowed(profile, 101)
    try:
        assert_vm_allowed(profile, 102)
    except PermissionError:
        pass
    else:
        raise AssertionError("VM não atribuída deveria ter sido bloqueada")


def test_admin_can_access_any_vmid():
    profile = UserProfile(role=Role.ADMIN, assigned_vmids=[])
    assert_vm_allowed(profile, 999)
