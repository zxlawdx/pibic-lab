from pibic_lab_core.security.hostkeys import find_host_key_line, host_pattern, replace_host_key


def test_host_pattern_default_and_custom_port():
    assert host_pattern("10.0.0.1", 22) == "10.0.0.1"
    assert host_pattern("10.0.0.1", 2222) == "[10.0.0.1]:2222"


def test_replace_only_target_host(tmp_path):
    path = tmp_path / "known_hosts"
    replace_host_key(path, "10.0.0.1", 22, "ssh-ed25519 AAAAOLD")
    replace_host_key(path, "10.0.0.2", 22, "ssh-ed25519 BBBB")
    replace_host_key(path, "10.0.0.1", 22, "ssh-ed25519 AAAANEW")
    text = path.read_text(encoding="utf-8")
    assert "AAAAOLD" not in text
    assert "AAAANEW" in text
    assert "BBBB" in text
    assert "AAAANEW" in find_host_key_line(path, "10.0.0.1", 22)
