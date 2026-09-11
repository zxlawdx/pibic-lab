"""Adaptador HTTP local entre o frontend Vela e o core do PIBIC LAB."""
from __future__ import annotations

from typing import Any, Callable

from pydantic import ValidationError
from vela.api import api

from pibic_lab_core.application.facade import AppFacade

facade = AppFacade()


def _json(context: dict | None) -> dict[str, Any]:
    if not context:
        return {}
    data = context.get("json") or {}
    return data if isinstance(data, dict) else {}


def _required(data: dict[str, Any], *fields: str) -> None:
    missing = [field for field in fields if data.get(field) in (None, "")]
    if missing:
        raise ValueError("Campos obrigatórios: " + ", ".join(missing))


def _call(fn: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"ok": True, "data": fn()}
    except ValidationError as exc:
        return {"ok": False, "error": "Dados inválidos.", "details": exc.errors(include_url=False)}
    except (ValueError, PermissionError, RuntimeError, FileNotFoundError, TimeoutError) as exc:
        message = str(exc).strip()
        if not message:
            message = f"{type(exc).__name__} sem mensagem"
        return {
            "ok": False,
            "error": message,
        }
    except Exception as exc:
        # A UI recebe uma mensagem curta; logs de desenvolvimento podem capturar o traceback.
        return {"ok": False, "error": f"Falha inesperada: {type(exc).__name__}: {exc}"}


@api.get("/lab/bootstrap/")
def bootstrap(context=None):
    return _call(lambda: facade.bootstrap())


@api.post("/lab/bootstrap/")
def bootstrap_selected(context=None):
    data = _json(context)
    return _call(lambda: facade.bootstrap(data.get("profile_id"), data.get("environment_id")))


@api.post("/lab/connectivity/")
def connectivity(context=None):
    data = _json(context)
    _required(data, "environment_id")
    return _call(lambda: facade.connectivity(int(data["environment_id"])))


@api.post("/lab/zerotier/join/")
def zerotier_join(context=None):
    data = _json(context)
    _required(data, "environment_id", "network_id")
    return _call(lambda: facade.zerotier_join(int(data["environment_id"]), str(data["network_id"])))


@api.post("/lab/profile/save/")
def profile_save(context=None):
    data = _json(context)
    return _call(lambda: facade.save_profile(data))


@api.post("/lab/environment/save/")
def environment_save(context=None):
    data = _json(context)
    return _call(lambda: facade.save_environment(data))


@api.post("/lab/ssh/preferences/")
def ssh_preferences(context=None):
    data = _json(context)
    _required(data, "profile_id")
    return _call(lambda: facade.save_connection_preferences(int(data["profile_id"]), data))


@api.post("/lab/ssh/probe/")
def ssh_probe(context=None):
    data = _json(context)
    _required(data, "environment_id")
    return _call(lambda: facade.ssh_probe(int(data["environment_id"])))


@api.post("/lab/ssh/trust/")
def ssh_trust(context=None):
    data = _json(context)
    _required(data, "profile_id", "host_key")
    return _call(lambda: facade.ssh_trust(data["host_key"], int(data["profile_id"])))


@api.post("/lab/ssh/connect/")
def ssh_connect(context=None):
    data = _json(context)
    _required(data, "profile_id", "environment_id")
    return _call(
        lambda: facade.ssh_connect(int(data["profile_id"]), int(data["environment_id"]), data)
    )


@api.post("/lab/ssh/disconnect/")
def ssh_disconnect(context=None):
    data = _json(context)
    _required(data, "profile_id")
    return _call(lambda: facade.ssh_disconnect(int(data["profile_id"])))


@api.post("/lab/ssh/status/")
def ssh_status(context=None):
    data = _json(context)
    _required(data, "profile_id")
    return _call(lambda: facade.ssh_status(int(data["profile_id"])))


@api.post("/lab/terminal/open/")
def terminal_open(context=None):
    data = _json(context)
    _required(data, "profile_id")
    return _call(
        lambda: facade.terminal_open(
            int(data["profile_id"]), int(data.get("cols", 100)), int(data.get("rows", 30))
        )
    )


@api.post("/lab/terminal/input/")
def terminal_input(context=None):
    data = _json(context)
    _required(data, "profile_id", "session_id", "data_b64")
    return _call(
        lambda: facade.terminal_input(int(data["profile_id"]), str(data["session_id"]), str(data["data_b64"]))
    )


@api.post("/lab/terminal/resize/")
def terminal_resize(context=None):
    data = _json(context)
    _required(data, "profile_id", "session_id", "cols", "rows")
    return _call(
        lambda: facade.terminal_resize(
            int(data["profile_id"]), str(data["session_id"]), int(data["cols"]), int(data["rows"])
        )
    )


@api.post("/lab/terminal/poll/")
def terminal_poll(context=None):
    data = _json(context)
    _required(data, "profile_id", "session_id")
    return _call(lambda: facade.terminal_poll(int(data["profile_id"]), str(data["session_id"])))


@api.post("/lab/terminal/close/")
def terminal_close(context=None):
    data = _json(context)
    _required(data, "profile_id", "session_id")
    return _call(lambda: facade.terminal_close(int(data["profile_id"]), str(data["session_id"])))


@api.post("/lab/dashboard/")
def dashboard(context=None):
    data = _json(context)
    _required(data, "profile_id")
    return _call(lambda: facade.dashboard(int(data["profile_id"])))


@api.post("/lab/services/detect/")
def services_detect(context=None):
    data = _json(context)
    _required(data, "profile_id")
    return _call(lambda: facade.detect_services(int(data["profile_id"])))


@api.get("/lab/catalog/")
def catalog(context=None):
    return _call(facade.catalog_list)


@api.post("/lab/catalog/plan/")
def catalog_plan(context=None):
    data = _json(context)
    _required(data, "profile_id", "manifest_id")
    return _call(lambda: facade.catalog_plan(int(data["profile_id"]), str(data["manifest_id"])))


@api.post("/lab/catalog/install/")
def catalog_install(context=None):
    data = _json(context)
    _required(data, "profile_id", "manifest_id")
    return _call(
        lambda: facade.catalog_install(int(data["profile_id"]), str(data["manifest_id"]), data)
    )


@api.get("/lab/jobs/")
def jobs(context=None):
    return _call(facade.jobs)


@api.post("/lab/docker/list/")
def docker_list(context=None):
    data = _json(context)
    _required(data, "profile_id")
    return _call(lambda: facade.docker_list(int(data["profile_id"])))


@api.post("/lab/docker/action/")
def docker_action(context=None):
    data = _json(context)
    _required(data, "profile_id", "container_id", "action")
    return _call(
        lambda: facade.docker_action(
            int(data["profile_id"]), str(data["container_id"]), str(data["action"]), bool(data.get("confirmed"))
        )
    )


@api.post("/lab/proxmox/credentials/")
def proxmox_credentials(context=None):
    data = _json(context)
    _required(data, "profile_id", "api_user", "token_name")
    return _call(
        lambda: facade.save_proxmox_credentials(
            int(data["profile_id"]),
            str(data["api_user"]),
            str(data["token_name"]),
            str(data.get("token_secret") or ""),
        )
    )


@api.post("/lab/proxmox/secret/delete/")
def proxmox_secret_delete(context=None):
    data = _json(context)
    _required(data, "profile_id")
    return _call(lambda: facade.delete_proxmox_secret(int(data["profile_id"])))


@api.post("/lab/proxmox/list/")
def proxmox_list(context=None):
    data = _json(context)
    _required(data, "profile_id", "environment_id")
    return _call(lambda: facade.proxmox_list(int(data["profile_id"]), int(data["environment_id"])))


@api.post("/lab/proxmox/create/options/")
def proxmox_create_options(context=None):
    data = _json(context)

    _required(
        data,
        "profile_id",
        "environment_id",
    )

    return _call(
        lambda: facade.proxmox_creation_options(
            int(data["profile_id"]),
            int(data["environment_id"]),
        )
    )


@api.post("/lab/proxmox/task/cancel/")
def proxmox_task_cancel(context=None):
    data = _json(context)
    _required(data, "profile_id", "environment_id", "node", "upid")
    return _call(lambda: facade.proxmox_task_cancel(int(data["profile_id"]), int(data["environment_id"]), data))


@api.post("/lab/proxmox/create/")
def proxmox_create(context=None):
    data = _json(context)

    _required(
        data,
        "profile_id",
        "environment_id",
        "vmid",
        "node",
        "name",
        "storage",
    )

    return _call(
        lambda: facade.proxmox_create_vm(
            int(data["profile_id"]),
            int(data["environment_id"]),
            data,
        )
    )


@api.post("/lab/proxmox/install/options/")
def proxmox_install_options(context=None):
    data = _json(context)
    _required(data, "profile_id", "environment_id")
    return _call(lambda: facade.proxmox_install_options(int(data["profile_id"]), int(data["environment_id"])))


@api.post("/lab/proxmox/install/node-options/")
def proxmox_node_options(context=None):
    data = _json(context)
    _required(data, "profile_id", "environment_id", "node")
    return _call(lambda: facade.proxmox_node_options(int(data["profile_id"]), int(data["environment_id"]), str(data["node"])))


@api.post("/lab/proxmox/iso/query/")
def proxmox_iso_query(context=None):
    data = _json(context)
    _required(data, "profile_id", "environment_id", "node", "url")
    return _call(lambda: facade.proxmox_iso_query(int(data["profile_id"]), int(data["environment_id"]), data))


@api.post("/lab/proxmox/iso/download/")
def proxmox_iso_download(context=None):
    data = _json(context)
    _required(data, "profile_id", "environment_id", "node", "storage", "url", "filename")
    return _call(lambda: facade.proxmox_iso_download(int(data["profile_id"]), int(data["environment_id"]), data))


@api.post("/lab/proxmox/task/status/")
def proxmox_task_status(context=None):
    data = _json(context)
    _required(data, "profile_id", "environment_id", "node", "upid")
    return _call(lambda: facade.proxmox_task_status(int(data["profile_id"]), int(data["environment_id"]), data))


@api.post("/lab/proxmox/clone/")
def proxmox_clone_vm(context=None):
    data = _json(context)
    _required(data, "profile_id", "environment_id", "vmid", "source_vmid", "source_node", "node", "name", "storage")
    return _call(lambda: facade.proxmox_clone_vm(int(data["profile_id"]), int(data["environment_id"]), data))


@api.post("/lab/proxmox/web/open/")
def proxmox_web_open(context=None):
    data = _json(context)
    _required(data, "profile_id", "environment_id")
    return _call(lambda: facade.proxmox_web_open(int(data["profile_id"]), int(data["environment_id"])))


@api.post("/lab/proxmox/action/")
def proxmox_action(context=None):
    data = _json(context)
    _required(data, "profile_id", "environment_id", "vmid", "node", "action")
    return _call(
        lambda: facade.proxmox_action(int(data["profile_id"]), int(data["environment_id"]), data)
    )


@api.post("/lab/logs/")
def logs(context=None):
    data = _json(context)
    _required(data, "profile_id")
    return _call(lambda: facade.logs(int(data["profile_id"]), int(data.get("limit", 200))))


@api.post("/lab/diagnostics/export/")
def diagnostics_export(context=None):
    data = _json(context)
    _required(data, "profile_id", "environment_id")
    return _call(
        lambda: facade.export_diagnostics(int(data["profile_id"]), int(data["environment_id"]))
    )


@api.get("/lab/settings/")
def settings(context=None):
    return _call(facade.settings)


@api.post("/lab/settings/save/")
def settings_save(context=None):
    data = _json(context)
    return _call(lambda: facade.save_settings(data))

@api.post("/lab/settings/")
def settings_save(context=None):
    data = _json(context)
    return _call(lambda: facade.save_settings(data))
