"""Workspace multiusuário sobre a sessão SSH já autenticada do PIBIC LAB.

Cada instância do Workspace é iniciada pelo próprio usuário SSH em uma porta
loopback aleatória. Assim, HOME, UID, shell, terminal e gerenciador de arquivos
passam a refletir a conta Linux do integrante, sem expor a porta na rede.
"""
from __future__ import annotations

import secrets
import shlex
from typing import Any
from urllib.parse import quote


def _parse_kv(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in str(text or "").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def _probe_command() -> str:
    return r"""sh -c '
ROOT=/opt/pibic-workspace
STATE="$HOME/.local/state/pibic-workspace/launcher"
printf "REMOTE_USER=%s\n" "$(id -un)"
printf "REMOTE_UID=%s\n" "$(id -u)"

if [ -r "$ROOT/app/main.py" ] && [ -r "$ROOT/web/index.html" ]; then
    echo "INSTALL_OK=1"
else
    echo "INSTALL_OK=0"
fi

if [ -x "$ROOT/.venv/bin/python" ]; then
    PY="$ROOT/.venv/bin/python"
elif [ -x "$ROOT/venv/bin/python" ]; then
    PY="$ROOT/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
else
    PY=""
fi
printf "PYTHON=%s\n" "$PY"

PORT=""
PID=""
[ -r "$STATE/port" ] && PORT="$(cat "$STATE/port" 2>/dev/null || true)"
[ -r "$STATE/pid" ] && PID="$(cat "$STATE/pid" 2>/dev/null || true)"
printf "PORT=%s\n" "$PORT"
printf "PID=%s\n" "$PID"

RUNNING=0
if [ -n "$PORT" ] && [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    if command -v wget >/dev/null 2>&1; then
        if wget -qO- -T 2 "http://127.0.0.1:$PORT/api/health" 2>/dev/null | grep -q "pibic-workspace"; then
            RUNNING=1
        fi
    elif [ -n "$PY" ]; then
        if "$PY" -c "import urllib.request; data=urllib.request.urlopen('http://127.0.0.1:$PORT/api/health', timeout=2).read().decode(); raise SystemExit(0 if 'pibic-workspace' in data else 1)" >/dev/null 2>&1; then
            RUNNING=1
        fi
    fi
fi
printf "RUNNING=%s\n" "$RUNNING"
'"""


def _stop_command() -> str:
    return r"""sh -c '
STATE="$HOME/.local/state/pibic-workspace/launcher"
if [ -r "$STATE/pid" ]; then
    PID="$(cat "$STATE/pid" 2>/dev/null || true)"
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null || true
        i=0
        while kill -0 "$PID" 2>/dev/null && [ "$i" -lt 20 ]; do
            sleep 0.1
            i=$((i + 1))
        done
    fi
fi
rm -f "$STATE/pid" "$STATE/port" "$STATE/access.token"
echo "STOPPED=1"
'"""


def _start_command(access_token: str) -> str:
    token = shlex.quote(access_token)
    return rf"""sh -c '
set -u
ROOT=/opt/pibic-workspace
STATE="$HOME/.local/state/pibic-workspace/launcher"
TOKEN={token}
umask 077
mkdir -p "$STATE" || exit 20
chmod 700 "$STATE" 2>/dev/null || true

if [ -x "$ROOT/.venv/bin/python" ]; then
    PY="$ROOT/.venv/bin/python"
elif [ -x "$ROOT/venv/bin/python" ]; then
    PY="$ROOT/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
else
    echo "ERROR=python3 não encontrado"
    exit 21
fi

if [ ! -r "$ROOT/app/main.py" ] || [ ! -r "$ROOT/web/index.html" ]; then
    echo "ERROR=Workspace não está legível por este usuário"
    exit 22
fi

if [ -r "$STATE/pid" ]; then
    OLD_PID="$(cat "$STATE/pid" 2>/dev/null || true)"
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null || true
        sleep 0.2
    fi
fi

PORT="$("$PY" -c "import socket; s=socket.socket(); s.bind(('127.0.0.1', 0)); print(s.getsockname()[1]); s.close()")" || exit 23
printf "%s\n" "$PORT" > "$STATE/port"
printf "%s\n" "$TOKEN" > "$STATE/access.token"
chmod 600 "$STATE/port" "$STATE/access.token" 2>/dev/null || true

cd "$ROOT" || exit 24
PIBIC_WORKSPACE_ACCESS_TOKEN="$TOKEN" \
nohup "$PY" -m uvicorn app.main:app \
    --host 127.0.0.1 \
    --port "$PORT" \
    --workers 1 \
    --no-proxy-headers \
    --log-level warning \
    > "$STATE/server.log" 2>&1 < /dev/null &
PID=$!
printf "%s\n" "$PID" > "$STATE/pid"
chmod 600 "$STATE/pid" 2>/dev/null || true

i=0
while [ "$i" -lt 15 ]; do
    if ! kill -0 "$PID" 2>/dev/null; then
        break
    fi

    READY=0
    if command -v wget >/dev/null 2>&1; then
        if wget -qO- -T 2 "http://127.0.0.1:$PORT/api/health" 2>/dev/null | grep -q "pibic-workspace"; then
            READY=1
        fi
    else
        if "$PY" -c "import urllib.request; data=urllib.request.urlopen('http://127.0.0.1:$PORT/api/health', timeout=2).read().decode(); raise SystemExit(0 if 'pibic-workspace' in data else 1)" >/dev/null 2>&1; then
            READY=1
        fi
    fi

    if [ "$READY" = "1" ]; then
        printf "REMOTE_USER=%s\n" "$(id -un)"
        printf "REMOTE_UID=%s\n" "$(id -u)"
        printf "PORT=%s\n" "$PORT"
        printf "PID=%s\n" "$PID"
        echo "RUNNING=1"
        exit 0
    fi

    sleep 0.4
    i=$((i + 1))
done

echo "ERROR=Workspace não iniciou a tempo"
tail -n 20 "$STATE/server.log" 2>/dev/null || true
kill "$PID" 2>/dev/null || true
rm -f "$STATE/pid" "$STATE/port" "$STATE/access.token"
exit 25
'"""


def _instance_state(self, profile_id: int) -> dict[str, Any]:
    result = self.ssh.run_command(profile_id, _probe_command(), timeout=8)
    values = _parse_kv(result.get("stdout") or "")
    return {
        "exit_status": result.get("exit_status"),
        "error": (result.get("stderr") or "").strip(),
        "remote_user": values.get("REMOTE_USER") or "",
        "remote_uid": int(values["REMOTE_UID"]) if values.get("REMOTE_UID", "").isdigit() else None,
        "install_ok": values.get("INSTALL_OK") == "1",
        "python": values.get("PYTHON") or "",
        "running": values.get("RUNNING") == "1",
        "remote_port": int(values["PORT"]) if values.get("PORT", "").isdigit() else None,
        "pid": int(values["PID"]) if values.get("PID", "").isdigit() else None,
    }


def _stop_instance(self, profile_id: int) -> None:
    if not self.ssh.is_connected(profile_id):
        return
    try:
        self.ssh.run_command(profile_id, _stop_command(), timeout=6)
    except Exception:
        pass


def _start_instance(self, profile_id: int) -> dict[str, Any]:
    access_token = secrets.token_urlsafe(32)
    result = self.ssh.run_command(profile_id, _start_command(access_token), timeout=16)
    output = (result.get("stdout") or "").strip()
    values = _parse_kv(output)

    if result.get("exit_status") != 0 or values.get("RUNNING") != "1":
        error = values.get("ERROR") or (result.get("stderr") or "").strip()
        if not error:
            error = output[-1200:] or "Falha ao iniciar o Workspace do usuário SSH."
        raise RuntimeError(error)

    port = values.get("PORT", "")
    if not port.isdigit():
        raise RuntimeError("Workspace iniciou sem informar uma porta válida.")

    return {
        "remote_user": values.get("REMOTE_USER") or self.ssh.status(profile_id).get("username") or "",
        "remote_uid": int(values["REMOTE_UID"]) if values.get("REMOTE_UID", "").isdigit() else None,
        "remote_port": int(port),
        "pid": int(values["PID"]) if values.get("PID", "").isdigit() else None,
        "access_token": access_token,
    }


def workspace_status(self, profile_id: int) -> dict[str, Any]:
    """Valida se o Workspace pode ser executado pelo usuário SSH conectado."""
    profile = self._profile(profile_id)

    if not self.ssh.is_connected(profile_id):
        return {
            "available": False,
            "connected": False,
            "message": "Conecte o SSH antes de acessar o Workspace.",
        }

    state = _instance_state(self, profile_id)
    available = bool(state["install_ok"] and state["python"])
    username = state["remote_user"] or self.ssh.status(profile_id).get("username") or ""

    if not available:
        message = (
            "O Alpine Workspace não está instalado em /opt/pibic-workspace "
            "ou o Python não está disponível para este usuário."
        )
    elif state["running"]:
        message = f"Workspace de {username} está em execução."
    else:
        message = f"Workspace pronto para iniciar como {username}."

    return {
        "available": available,
        "connected": True,
        "profile_id": profile_id,
        "profile": profile.display_name,
        "remote_user": username,
        "remote_uid": state["remote_uid"],
        "remote_host": "127.0.0.1",
        "remote_port": state["remote_port"],
        "running": state["running"],
        "isolated_user": True,
        "message": message,
        "error": state["error"][:1000] if state["error"] else None,
    }


def workspace_open(self, profile_id: int) -> dict[str, Any]:
    """Inicia/reutiliza a instância do usuário SSH e cria Local Port Forward."""
    profile = self._profile(profile_id)

    if not self.ssh.is_connected(profile_id):
        raise RuntimeError("Conecte o SSH antes de abrir o PIBIC Workspace.")

    status = workspace_status(self, profile_id)
    if not status.get("available"):
        raise RuntimeError(status.get("message") or "PIBIC Workspace indisponível.")

    old = self._workspace_forwards.pop(profile_id, None)
    if old:
        try:
            self.ssh.close_forward(profile_id, old["forward_id"])
        except Exception:
            pass

    instance: dict[str, Any] | None = None
    if (
        old
        and status.get("running")
        and old.get("remote_port") == status.get("remote_port")
        and old.get("access_token")
    ):
        instance = {
            "remote_user": old.get("remote_user") or status.get("remote_user") or "",
            "remote_uid": old.get("remote_uid") or status.get("remote_uid"),
            "remote_port": int(old["remote_port"]),
            "pid": old.get("remote_pid"),
            "access_token": old["access_token"],
        }

    if instance is None:
        if status.get("running"):
            _stop_instance(self, profile_id)
        instance = _start_instance(self, profile_id)

    forward = self.ssh.open_forward(
        profile_id,
        "127.0.0.1",
        int(instance["remote_port"]),
    )

    stored = {
        **forward,
        "remote_port": int(instance["remote_port"]),
        "remote_user": instance.get("remote_user") or "",
        "remote_uid": instance.get("remote_uid"),
        "remote_pid": instance.get("pid"),
        "access_token": instance["access_token"],
    }
    self._workspace_forwards[profile_id] = stored

    token = quote(str(instance["access_token"]), safe="")
    url = f"http://127.0.0.1:{forward['local_port']}/?access_token={token}"

    self.audit.log(
        "workspace",
        "open",
        profile.display_name,
        target=f"{instance.get('remote_user') or 'ssh-user'}@127.0.0.1:{instance['remote_port']}",
        details={
            "local_port": forward["local_port"],
            "remote_port": instance["remote_port"],
            "remote_user": instance.get("remote_user"),
            "remote_uid": instance.get("remote_uid"),
            "isolated_user": True,
        },
    )

    return {
        "available": True,
        "url": url,
        "local_host": "127.0.0.1",
        "local_port": forward["local_port"],
        "remote_host": "127.0.0.1",
        "remote_port": instance["remote_port"],
        "remote_user": instance.get("remote_user") or "",
        "remote_uid": instance.get("remote_uid"),
        "forward_id": forward["forward_id"],
        "isolated_user": True,
        "message": f"Workspace aberto como {instance.get('remote_user') or 'usuário SSH'}.",
    }


def workspace_close(self, profile_id: int) -> dict[str, Any]:
    """Fecha o forward e encerra apenas a instância do usuário SSH atual."""
    forward = self._workspace_forwards.pop(profile_id, None)

    if forward:
        try:
            self.ssh.close_forward(profile_id, forward["forward_id"])
        except Exception:
            pass

    _stop_instance(self, profile_id)

    return {
        "closed": True,
        "message": "Forward e instância do Workspace encerrados.",
    }


def ssh_disconnect(self, profile_id: int) -> dict[str, Any]:
    """Limpa a instância do Workspace antes de encerrar a sessão SSH."""
    profile = self._profile(profile_id)
    if self.ssh.is_connected(profile_id):
        try:
            workspace_close(self, profile_id)
        except Exception:
            pass
    self.ssh.disconnect(profile_id)
    self.audit.log("ssh", "disconnect", profile.display_name)
    return {"ok": True}


def install_workspace_multiuser(app_facade_class) -> None:
    """Aplica a integração sem alterar as demais responsabilidades do AppFacade."""
    if getattr(app_facade_class, "_workspace_multiuser_installed", False):
        return

    app_facade_class._workspace_multiuser_installed = True
    app_facade_class.VERSION = "0.1.3"
    app_facade_class.workspace_status = workspace_status
    app_facade_class.workspace_open = workspace_open
    app_facade_class.workspace_close = workspace_close
    app_facade_class.ssh_disconnect = ssh_disconnect
