from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_frontend_boots_when_domcontentloaded_already_happened():
    app_js = (ROOT / "apps" / "lab" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "document.readyState === 'loading'" in app_js
    assert "window.__PIBIC_LAB_ACTIVE_ROOT__" in app_js
    assert "boot();" in app_js


def test_project_contains_vela_bridge_and_shell_recovery():
    compat = (ROOT / "pibic_lab_core" / "vela_compat.py").read_text(encoding="utf-8")
    assert "class PIBICBridge" in compat
    assert "def get_config" in compat
    assert "class ResilientDesktopWindow" in compat
    assert "window.Vela._initialized = false" in compat


def test_wsgi_installs_compatibility_before_running_app():
    wsgi = (ROOT / "config" / "wsgi.py").read_text(encoding="utf-8")
    assert "install_vela_window_patch()" in wsgi
    assert "app.bridge = PIBICBridge" in wsgi
