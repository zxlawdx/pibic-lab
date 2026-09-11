"""Camada de aplicação do PIBIC LAB."""

from .facade import AppFacade
from .workspace_multiuser import install_workspace_multiuser

install_workspace_multiuser(AppFacade)

__all__ = ["AppFacade"]
