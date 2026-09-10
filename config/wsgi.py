"""Boot da aplicação Vela."""
from __future__ import annotations

from vela.core.app import VelaApp

# O Vela registra endpoints @api.* no momento do import.
import apps.lab.api  # noqa: F401, E402

from pibic_lab_core.vela_compat import PIBICBridge, install_vela_window_patch  # noqa: E402

INSTALLED_APPS = ["apps.lab"]


def run() -> None:
    # Corrige uma condição de corrida do shell em GTK/WebKit sem tocar no
    # site-packages do usuário. A correção também é inofensiva no Windows/Qt.
    install_vela_window_patch()

    app = VelaApp(settings_module="config.settings")

    # Substitui o bridge criado pelo Vela por uma implementação explícita da API
    # mínima esperada pela shell. Isso mantém compatibilidade mesmo quando uma
    # instalação antiga do framework ficou no .venv.
    app.bridge = PIBICBridge(router=app.router, config=app._config)

    for app_name in INSTALLED_APPS:
        app.register_app(app_name)
    app.run()
