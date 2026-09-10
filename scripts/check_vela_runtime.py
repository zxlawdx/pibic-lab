"""Diagnóstico rápido do Vela/pywebview instalado no ambiente atual."""
from __future__ import annotations

import inspect
import sys

import vela
import webview
from vela.core.bridge import BaseBridge


print("Python:", sys.version.split()[0])
print("Vela:", getattr(vela, "__version__", "sem __version__"), vela.__file__)
print("pywebview:", getattr(webview, "__version__", "versão não exposta"))
print("BaseBridge.get_config:", hasattr(BaseBridge, "get_config"))
print("BaseBridge.get_routes:", hasattr(BaseBridge, "get_routes"))
print("BaseBridge.navigate:", hasattr(BaseBridge, "navigate"))
if hasattr(BaseBridge, "get_config"):
    print("get_config definido em:", inspect.getsourcefile(BaseBridge.get_config))
