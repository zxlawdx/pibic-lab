"""Camada de aplicação do PIBIC LAB."""

from .facade import AppFacade
from . import workspace_multiuser as _workspace_multiuser
from .workspace_shell_fix import apply_workspace_shell_fix

apply_workspace_shell_fix(_workspace_multiuser)
_workspace_multiuser.install_workspace_multiuser(AppFacade)

__all__ = ["AppFacade"]
