"""Configurações globais da janela Vela."""
from __future__ import annotations

APP_TITLE = "PIBIC LAB"
ENTRY_ROUTE = "/"
WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900
WINDOW_MIN_WIDTH = 1120
WINDOW_MIN_HEIGHT = 720

# A navegação é desenhada pela própria aplicação para permitir SVGs e uma UX consistente.
LAYOUT = {
    "sidebar": False,
    "topbar": False,
    "theme": "dark",
}

DEBUG = False
STATIC_ROOT = "staticfiles"
