from pathlib import Path

from pibic_lab_core.domain.models import RemoteSystemInfo
from pibic_lab_core.infrastructure.catalog import CatalogRepository, PackageInstaller


ROOT = Path(__file__).resolve().parents[2]


def test_all_bundled_manifests_parse():
    items = CatalogRepository(ROOT / "catalog" / "manifests").list()
    assert {item.id for item in items} >= {"git", "python", "docker", "nginx", "postgresql"}
    for item in items:
        assert item.manifest_version == 1
        assert item.detect_command_id


def test_build_plan_generates_only_typed_commands():
    repo = CatalogRepository(ROOT / "catalog" / "manifests")
    manifest = repo.get("git")
    installer = object.__new__(PackageInstaller)
    plan = installer.build_plan(manifest, RemoteSystemInfo(os_id="debian", os_version="13"))
    assert plan.compatible is True
    assert plan.commands_preview == ["apt-get update", "apt-get install -y git"]
