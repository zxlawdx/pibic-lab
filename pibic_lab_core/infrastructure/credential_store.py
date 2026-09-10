"""Segredos no keyring nativo do sistema operacional.

Nenhum fallback para arquivo em texto puro é utilizado. Se o sistema não oferecer
um backend de keyring seguro, o aplicativo continua funcionando sem persistência
de segredos e informa o usuário quando ele tenta salvar uma credencial.
"""
from __future__ import annotations

import keyring
from keyring.errors import KeyringError, NoKeyringError, PasswordDeleteError

SERVICE = "PIBIC-LAB"


class CredentialStore:
    def _key(self, kind: str, profile_id: int) -> str:
        return f"{kind}:profile:{profile_id}"

    @staticmethod
    def _friendly_error(exc: Exception) -> RuntimeError:
        return RuntimeError(
            "O sistema operacional não disponibilizou um keyring seguro para salvar esta credencial. "
            "Use a credencial somente nesta sessão ou configure o cofre de senhas do sistema. "
            f"Detalhe: {type(exc).__name__}: {exc}"
        )

    def set_secret(self, kind: str, profile_id: int, value: str) -> None:
        if not value:
            self.delete_secret(kind, profile_id)
            return
        try:
            keyring.set_password(SERVICE, self._key(kind, profile_id), value)
        except (NoKeyringError, KeyringError) as exc:
            raise self._friendly_error(exc) from exc

    def get_secret(self, kind: str, profile_id: int) -> str | None:
        try:
            return keyring.get_password(SERVICE, self._key(kind, profile_id))
        except (NoKeyringError, KeyringError):
            # Consultas de bootstrap não devem impedir o aplicativo de abrir.
            return None

    def delete_secret(self, kind: str, profile_id: int) -> None:
        try:
            keyring.delete_password(SERVICE, self._key(kind, profile_id))
        except (PasswordDeleteError, NoKeyringError, KeyringError):
            pass

    def has_secret(self, kind: str, profile_id: int) -> bool:
        return self.get_secret(kind, profile_id) is not None
