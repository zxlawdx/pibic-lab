from pibic_lab_core.domain.models import Role, UserProfile
from pibic_lab_core.infrastructure.sqlite_store import SQLiteStore


def test_store_seeds_environment_and_profile(tmp_path):
    store = SQLiteStore(tmp_path / "app.sqlite3")
    envs = store.list_environments()
    profiles = store.list_profiles()
    assert envs[0].gateway_host == "10.57.144.217"
    assert envs[0].proxmox_internal_host == "10.99.0.59"
    assert profiles[0].role == Role.STUDENT


def test_profile_metadata_roundtrip(tmp_path):
    store = SQLiteStore(tmp_path / "app.sqlite3")
    profile = UserProfile(display_name="Teste", role=Role.ADVISOR, ssh_username="teste", assigned_vmids=[120])
    saved = store.save_profile(profile)
    loaded = store.get_profile(saved.id)
    assert loaded.display_name == "Teste"
    assert loaded.assigned_vmids == [120]
