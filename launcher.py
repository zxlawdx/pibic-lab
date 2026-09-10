"""
PIBIC LAB - Launcher do executável.

No desenvolvimento:
    python manage.py runapp

No executável:
    launcher.py -> config.wsgi.run()
"""

import os
import sys
from pathlib import Path


# ---------------------------------------------------------
# Diretório da aplicação
# ---------------------------------------------------------

if getattr(sys, "frozen", False):
    # Em builds PyInstaller --onedir, os arquivos adicionados com --add-data
    # ficam em sys._MEIPASS (normalmente a pasta _internal/).
    #
    # O Vela 0786ba3 ainda resolve templates e staticfiles a partir de
    # os.getcwd(). Portanto, no executável precisamos fazer o diretório de
    # trabalho apontar para o bundle, e não para a pasta onde o usuário
    # extraiu/abriu o executável.
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
    os.chdir(BASE_DIR)
else:
    BASE_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(BASE_DIR))


# ---------------------------------------------------------
# Backend gráfico
# ---------------------------------------------------------

if sys.platform == "win32":
    # No Windows, o Vela recomenda Qt para o executável.
    os.environ.setdefault("PYWEBVIEW_GUI", "qt")

    try:
        import webview

        _original_start = webview.start

        def start_qt(*args, **kwargs):
            kwargs.pop("gui", None)
            return _original_start(*args, gui="qt", **kwargs)

        webview.start = start_qt

    except Exception as exc:
        print(
            f"[PIBIC LAB] Não foi possível configurar Qt: {exc}",
            file=sys.stderr,
        )


# ---------------------------------------------------------
# Inicialização real do Vela
# ---------------------------------------------------------

# Imports explícitos para o PyInstaller não eliminar módulos
# carregados dinamicamente pelo Vela.
import config.settings  # noqa: F401
import config.wsgi      # noqa: F401

from config.wsgi import run


if __name__ == "__main__":
    run()
