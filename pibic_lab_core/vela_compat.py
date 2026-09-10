"""Compatibilidade do PIBIC LAB com o ciclo de vida do Vela/pywebview.

O Vela carrega as views dentro de ``#vela-page`` depois que o documento principal
já disparou ``DOMContentLoaded``. Além disso, em alguns backends GTK/WebKit a
existência de ``window.pywebview.api`` pode anteceder por alguns milissegundos a
criação das funções do bridge. Este módulo mantém a correção no projeto, sem
editar ``site-packages`` dos colegas.
"""
from __future__ import annotations

import json
import webbrowser
from urllib.parse import urlparse

import webview
from vela.core.bridge import BaseBridge
from vela.core.window import DesktopWindow
from vela.log.logger import VelaLogger


class PIBICBridge(BaseBridge):
    """Bridge compatível com versões recentes e intermediárias do Vela.

    Os métodos abaixo são definidos explicitamente mesmo quando já existem no
    ``BaseBridge``. Assim o shell sempre encontra a API mínima esperada pelo
    frontend: ``get_config``, ``get_routes``, ``navigate`` e ``url_for``.
    """

    def __init__(self, router=None, config: dict | None = None):
        # Não dependemos do __init__ de uma versão específica do BaseBridge.
        self.router = router
        self.config = config or {}
        self.logger = VelaLogger("Bridge")

    def get_config(self) -> dict:
        return self.config

    def get_routes(self) -> list:
        return self.router.get_sidebar_routes() if self.router else []

    def navigate(self, path: str, params: str = "{}") -> dict:
        if not self.router:
            return {"ok": False, "path": path, "error": "Router do Vela indisponível."}

        try:
            parsed_params = json.loads(params) if isinstance(params, str) else (params or {})
        except (json.JSONDecodeError, TypeError):
            parsed_params = {}

        try:
            result = self.router.resolve(path, parsed_params)
            self.logger.info(f"navigate() → {path} [layout={result.get('layout', 'default')}]")
            return {
                "ok": True,
                "html": result["html"],
                "layout": result.get("layout", "default"),
                "path": path,
            }
        except Exception as exc:  # o shell precisa receber um objeto serializável
            self.logger.error(f"Falha ao navegar para {path}: {exc}")
            return {"ok": False, "path": path, "error": str(exc)}

    def url_for(self, name: str) -> dict:
        if not self.router:
            return {"ok": False, "path": None, "error": "Router do Vela indisponível."}
        try:
            return {"ok": True, "path": self.router.url_for(name)}
        except KeyError as exc:
            return {"ok": False, "path": None, "error": str(exc)}

    def ping(self) -> str:
        return "pong"


    @staticmethod
    def _validated_local_proxmox_url(url: str) -> str:
        parsed = urlparse(str(url or ""))
        if parsed.scheme != "https" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("A janela Proxmox só pode abrir um túnel HTTPS local.")
        if not parsed.port or not 1 <= parsed.port <= 65535:
            raise ValueError("Porta local inválida.")
        return url

    def open_proxmox_window(self, url: str) -> dict:
        try:
            url = self._validated_local_proxmox_url(url)
            webview.create_window(
                "Proxmox VE · PIBIC LAB",
                url=url,
                width=1500,
                height=930,
                min_size=(1000, 700),
                resizable=True,
                zoomable=True,
                background_color="#0b111b",
            )
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def open_external_browser(self, url: str) -> dict:
        try:
            url = self._validated_local_proxmox_url(url)
            opened = bool(webbrowser.open(url, new=2))
            return {"ok": opened}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

class ResilientDesktopWindow(DesktopWindow):
    """DesktopWindow com recuperação do bootstrap da shell no GTK/WebKit.

    O shell do Vela pode observar ``window.pywebview.api`` antes de as funções
    como ``get_config`` estarem anexadas. O próprio pywebview dispara ``loaded``
    depois de concluir a criação da API. Nesse momento, esta classe verifica se
    o primeiro bootstrap falhou e reinicia o ``Vela.init()`` uma única vez.
    """

    def run(self):
        shell_url = self._get_shell_url()
        self.logger.info(f"Carregando shell resiliente [{self.shell_mode}]: {shell_url}")

        window = webview.create_window(
            title=self.title,
            url=shell_url,
            width=self.width,
            height=self.height,
            js_api=self.bridge,
            resizable=True,
            frameless=False,
            easy_drag=False,
        )

        entry_json = json.dumps(self.entry_route)
        recovery_script = f"""
            (() => {{
                window.__VELA_ENTRY__ = {entry_json};

                const apiReady = () => {{
                    const api = window.pywebview && window.pywebview.api;
                    return api
                        && typeof api.get_config === 'function'
                        && typeof api.get_routes === 'function'
                        && typeof api.navigate === 'function';
                }};

                const recover = () => {{
                    if (!window.Vela) return;
                    if (!apiReady()) {{
                        window.setTimeout(recover, 50);
                        return;
                    }}

                    // Se a rota já foi carregada, o bootstrap anterior funcionou.
                    if (window.Vela.currentPath) return;

                    // O shell marca _initialized antes de chamar get_config().
                    // Caso essa chamada tenha acontecido cedo demais, liberamos
                    // somente esse guard e repetimos a inicialização.
                    window.Vela._initialized = false;
                    Promise.resolve(window.Vela.init()).catch((error) =>
                        console.error('[PIBIC LAB] Falha na recuperação do Vela:', error)
                    );
                }};

                recover();
            }})();
        """

        def on_loaded():
            try:
                # ``run_js`` não depende do retorno de eval e funciona bem com CSP.
                if hasattr(window, "run_js"):
                    window.run_js(recovery_script)
                else:
                    window.evaluate_js(recovery_script)
            except Exception as exc:
                self.logger.error(f"Falha ao executar recuperação da shell: {exc}")

        window.events.loaded += on_loaded
        webview.start(debug=self.debug)
        self.logger.info("Janela encerrada.")


def install_vela_window_patch() -> None:
    """Faz VelaApp usar a janela resiliente sem alterar o pacote instalado."""

    import vela.core.app as vela_app_module

    if vela_app_module.DesktopWindow is not ResilientDesktopWindow:
        vela_app_module.DesktopWindow = ResilientDesktopWindow
        VelaLogger("Compat").info("Compatibilidade GTK/pywebview ativada.")
