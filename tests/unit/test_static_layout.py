from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_vela_static_layout_has_no_duplicate_app_namespace():
    assert not (ROOT / "apps" / "lab" / "static" / "lab").exists()


def test_required_frontend_assets_exist_at_vela_source_paths():
    required = [
        ROOT / "apps" / "lab" / "static" / "css" / "app.css",
        ROOT / "apps" / "lab" / "static" / "js" / "icons.js",
        ROOT / "apps" / "lab" / "static" / "js" / "app.js",
        ROOT / "apps" / "lab" / "static" / "vendor" / "xterm" / "xterm.css",
    ]
    for path in required:
        assert path.is_file(), f"Asset ausente: {path.relative_to(ROOT)}"
        assert path.stat().st_size > 0, f"Asset vazio: {path.relative_to(ROOT)}"


def test_template_uses_paths_expected_after_collectstatic():
    template = (ROOT / "apps" / "lab" / "templates" / "index.html").read_text(encoding="utf-8")
    assert "static('lab/css/app.css')" in template
    assert "static('lab/js/icons.js')" in template
    assert "static('lab/js/app.js')" in template
    assert "static('lab/vendor/xterm/xterm.css')" in template
