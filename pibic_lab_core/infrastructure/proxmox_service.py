"""Cliente Proxmox via API HTTPS roteada por SOCKS sobre a sessão SSH.

O SOCKS preserva o hostname/IP interno na conexão TLS, evitando o problema de
validar um certificado do Proxmox contra 127.0.0.1 em um local-forward comum.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from urllib.parse import quote, urlparse

import requests

from pibic_lab_core.domain.models import AppSettings, Environment, ProxmoxVM, Role, UserProfile
from pibic_lab_core.domain.permissions import assert_vm_allowed, permissions_for
from pibic_lab_core.util.commands import validate_identifier


class ProxmoxService:
    def __init__(self, ssh, audit) -> None:
        self.ssh = ssh
        self.audit = audit
        self._web_forwards: dict[int, dict[str, Any]] = {}

    @staticmethod
    def _verify_value(settings: AppSettings) -> bool | str:
        if settings.verify_proxmox_tls:
            if settings.proxmox_ca_path:
                path = Path(settings.proxmox_ca_path).expanduser()
                if not path.exists():
                    raise FileNotFoundError(f"CA do Proxmox não encontrada: {path}")
                return str(path)
            return True
        if not settings.allow_unsafe_proxmox_tls:
            raise PermissionError(
                "TLS sem validação está bloqueado. Configure a CA do Proxmox ou habilite explicitamente o modo inseguro."
            )
        return False

    @staticmethod
    def _headers(api_user: str, token_name: str, token_secret: str) -> dict[str, str]:
        if not api_user or not token_name or not token_secret:
            raise ValueError("Credenciais de API do Proxmox não configuradas.")
        validate_identifier(api_user, "usuário da API")
        validate_identifier(token_name, "nome do token")
        return {"Authorization": f"PVEAPIToken={api_user}!{token_name}={token_secret}"}

    def _request(
        self,
        *,
        profile_id: int,
        environment: Environment,
        api_user: str,
        token_name: str,
        token_secret: str,
        settings: AppSettings,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        socks = self.ssh.open_socks(profile_id)
        proxy = f"socks5h://127.0.0.1:{socks['local_port']}"
        url = f"https://{environment.proxmox_internal_host}:{environment.proxmox_port}/api2/json{path}"
        session = requests.Session()
        session.trust_env = False
        session.proxies.update({"http": proxy, "https": proxy})
        try:
            response = session.request(
                method,
                url,
                headers=self._headers(api_user, token_name, token_secret),
                data=data,
                params=params,
                timeout=(8, 20),
                verify=self._verify_value(settings),
            )
            if response.status_code >= 400:
                detail = response.text[:500]
                raise RuntimeError(f"Proxmox API retornou HTTP {response.status_code}: {detail}")
            payload = response.json()
            return payload if isinstance(payload, dict) else {"data": payload}
        finally:
            session.close()
            self.ssh.close_forward(profile_id, socks["forward_id"])

    def list_vms(
        self,
        *,
        profile: UserProfile,
        environment: Environment,
        api_user: str,
        token_name: str,
        token_secret: str,
        settings: AppSettings,
    ) -> list[ProxmoxVM]:
        perms = permissions_for(profile)
        if not perms.proxmox_read:
            raise PermissionError("Perfil sem permissão para consultar Proxmox.")
        payload = self._request(
            profile_id=profile.id or 0,
            environment=environment,
            api_user=api_user,
            token_name=token_name,
            token_secret=token_secret,
            settings=settings,
            method="GET",
            path="/cluster/resources?type=vm",
        )
        vms: list[ProxmoxVM] = []
        for item in payload.get("data") or []:
            try:
                vmid = int(item.get("vmid"))
            except (TypeError, ValueError):
                continue
            if profile.role != Role.ADMIN and vmid not in profile.assigned_vmids:
                continue
            vms.append(
                ProxmoxVM(
                    vmid=vmid,
                    name=str(item.get("name") or f"VM {vmid}"),
                    node=item.get("node"),
                    status=item.get("status"),
                    cpu=item.get("cpu"),
                    maxcpu=item.get("maxcpu"),
                    mem=item.get("mem"),
                    maxmem=item.get("maxmem"),
                    disk=item.get("disk"),
                    maxdisk=item.get("maxdisk"),
                    uptime=item.get("uptime"),
                    vm_type=item.get("type"),
                )
            )
        return vms

    def creation_options(
        self,
        *,
        profile: UserProfile,
        environment: Environment,
        api_user: str,
        token_name: str,
        token_secret: str,
        settings: AppSettings,
    ) -> dict[str, Any]:
        """Compatibilidade com a primeira versão do formulário de criação."""
        data = self.installer_options(
            profile=profile,
            environment=environment,
            api_user=api_user,
            token_name=token_name,
            token_secret=token_secret,
            settings=settings,
        )
        node_opts = data.get("node_options") or {}
        return {
            "next_vmid": data["next_vmid"],
            "nodes": data["nodes"],
            "storages": [s["storage"] for s in node_opts.get("image_storages", [])],
            "default_bridge": (node_opts.get("bridges") or ["vmbr0"])[0],
        }

    def cancel_task(
        self,
        *,
        profile: UserProfile,
        environment: Environment,
        api_user: str,
        token_name: str,
        token_secret: str,
        settings: AppSettings,
        node: str,
        upid: str,
    ) -> dict[str, Any]:
        """Solicita ao Proxmox o cancelamento de uma task em execução.

        O Proxmox expõe DELETE /nodes/{node}/tasks/{upid}. Tasks iniciadas
        pelo próprio usuário/token normalmente podem ser interrompidas; para
        tasks de outros usuários o Proxmox pode exigir privilégio adicional.
        """
        if not permissions_for(profile).proxmox_read:
            raise PermissionError("Perfil sem permissão para operar tasks do Proxmox.")
        node = validate_identifier(node, "node")
        if not upid or len(upid) > 2048 or not upid.startswith("UPID:"):
            raise ValueError("UPID inválido.")
        self._request(
            profile_id=profile.id or 0,
            environment=environment,
            api_user=api_user,
            token_name=token_name,
            token_secret=token_secret,
            settings=settings,
            method="DELETE",
            path=f"/nodes/{node}/tasks/{quote(upid, safe='')}",
        )
        self.audit.log(
            "proxmox",
            "cancel_task",
            profile.display_name,
            target=upid,
            details={"node": node},
        )
        return {"ok": True, "node": node, "upid": upid}

    def create_vm(
        self,
        *,
        profile: UserProfile,
        environment: Environment,
        api_user: str,
        token_name: str,
        token_secret: str,
        settings: AppSettings,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        if profile.role != Role.ADMIN:
            raise PermissionError("Somente o Administrador do laboratório pode criar VMs.")
        if not bool(data.get("confirmed")):
            raise PermissionError("A criação da VM exige confirmação explícita.")

        node = validate_identifier(str(data.get("node") or ""), "node")
        storage = validate_identifier(str(data.get("storage") or ""), "storage")
        bridge = validate_identifier(str(data.get("bridge") or "vmbr0"), "bridge")
        name = str(data.get("name") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}", name):
            raise ValueError("Nome da VM deve usar letras, números e hífen e ter até 63 caracteres.")

        def integer(field: str, default: int) -> int:
            try:
                return int(data.get(field, default))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field} precisa ser um número inteiro.") from exc

        vmid = integer("vmid", 100)
        sockets = integer("sockets", 1)
        cores = integer("cores", 2)
        memory_mb = integer("memory_mb", 2048)
        balloon_mb = integer("balloon_mb", 0)
        disk_gb = integer("disk_gb", 20)
        vlan_tag = integer("vlan_tag", 0)

        if not 100 <= vmid <= 999999999:
            raise ValueError("VMID fora da faixa permitida.")
        if not 1 <= sockets <= 8 or not 1 <= cores <= 128:
            raise ValueError("Sockets/cores fora da faixa permitida.")
        if not 512 <= memory_mb <= 1048576:
            raise ValueError("Memória fora da faixa permitida.")
        if balloon_mb < 0 or balloon_mb > memory_mb:
            raise ValueError("Balloon deve ficar entre 0 e a memória máxima.")
        if not 4 <= disk_gb <= 16384:
            raise ValueError("Disco deve ficar entre 4 GB e 16384 GB.")
        if vlan_tag and not 1 <= vlan_tag <= 4094:
            raise ValueError("VLAN precisa ficar entre 1 e 4094.")

        ostype = str(data.get("ostype") or "l26")
        if ostype not in {"l26", "win11", "win10", "win8", "win7", "other"}:
            raise ValueError("Tipo de sistema operacional inválido.")
        machine = str(data.get("machine") or "q35")
        if machine not in {"q35", "pc"}:
            raise ValueError("Tipo de máquina inválido.")
        bios = str(data.get("bios") or "seabios")
        if bios not in {"seabios", "ovmf"}:
            raise ValueError("BIOS inválida.")
        cpu_type = str(data.get("cpu_type") or "x86-64-v2-AES").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.+-]{1,64}", cpu_type):
            raise ValueError("Tipo de CPU inválido.")
        disk_bus = str(data.get("disk_bus") or "scsi")
        if disk_bus not in {"scsi", "virtio", "sata"}:
            raise ValueError("Barramento de disco inválido.")
        net_model = str(data.get("net_model") or "virtio")
        if net_model not in {"virtio", "e1000", "rtl8139", "vmxnet3"}:
            raise ValueError("Modelo de placa de rede inválido.")

        disk_key = {"scsi": "scsi0", "virtio": "virtio0", "sata": "sata0"}[disk_bus]
        net0 = f"{net_model},bridge={bridge}"
        if vlan_tag:
            net0 += f",tag={vlan_tag}"
        if bool(data.get("firewall", True)):
            net0 += ",firewall=1"

        request_data: dict[str, Any] = {
            "vmid": vmid,
            "name": name,
            "sockets": sockets,
            "cores": cores,
            "cpu": cpu_type,
            "memory": memory_mb,
            "balloon": balloon_mb,
            "ostype": ostype,
            "machine": machine,
            "bios": bios,
            "scsihw": "virtio-scsi-pci",
            disk_key: f"{storage}:{disk_gb}",
            "net0": net0,
            "agent": 1 if bool(data.get("agent", True)) else 0,
            "onboot": 1 if bool(data.get("onboot", False)) else 0,
        }

        if bios == "ovmf":
            request_data["efidisk0"] = f"{storage}:1,efitype=4m,pre-enrolled-keys=1"

        iso = str(data.get("iso") or "").strip()
        if iso:
            if not re.fullmatch(r"[A-Za-z0-9_.-]+:iso/[A-Za-z0-9_.-]+", iso):
                raise ValueError("ISO inválida. Selecione uma ISO retornada pelo Proxmox.")
            request_data["ide2"] = f"{iso},media=cdrom"
            request_data["boot"] = f"order=ide2;{disk_key};net0"
        else:
            request_data["boot"] = f"order={disk_key};net0"

        payload = self._request(
            profile_id=profile.id or 0,
            environment=environment,
            api_user=api_user,
            token_name=token_name,
            token_secret=token_secret,
            settings=settings,
            method="POST",
            path=f"/nodes/{node}/qemu",
            data=request_data,
        )
        task_id = payload.get("data")
        self.audit.log(
            "proxmox", "create_vm", profile.display_name, target=str(vmid),
            details={
                "node": node, "name": name, "storage": storage, "iso": iso,
                "cores": cores, "sockets": sockets, "memory_mb": memory_mb,
                "disk_gb": disk_gb, "bridge": bridge, "task_id": task_id,
            },
        )
        return {"ok": True, "vmid": vmid, "name": name, "node": node, "task_id": task_id}

    def installer_options(
        self,
        *,
        profile: UserProfile,
        environment: Environment,
        api_user: str,
        token_name: str,
        token_secret: str,
        settings: AppSettings,
    ) -> dict[str, Any]:
        if profile.role != Role.ADMIN:
            raise PermissionError("Somente o Administrador do laboratório pode criar ou clonar VMs.")

        next_payload = self._request(
            profile_id=profile.id or 0,
            environment=environment,
            api_user=api_user,
            token_name=token_name,
            token_secret=token_secret,
            settings=settings,
            method="GET",
            path="/cluster/nextid",
        )
        resources_payload = self._request(
            profile_id=profile.id or 0,
            environment=environment,
            api_user=api_user,
            token_name=token_name,
            token_secret=token_secret,
            settings=settings,
            method="GET",
            path="/cluster/resources?type=vm",
        )
        nodes_payload = self._request(
            profile_id=profile.id or 0,
            environment=environment,
            api_user=api_user,
            token_name=token_name,
            token_secret=token_secret,
            settings=settings,
            method="GET",
            path="/nodes",
        )

        nodes = sorted(
            str(item.get("node"))
            for item in (nodes_payload.get("data") or [])
            if item.get("node")
        )
        vms = []
        for item in resources_payload.get("data") or []:
            if item.get("type") != "qemu":
                continue
            try:
                vmid = int(item.get("vmid"))
            except (TypeError, ValueError):
                continue
            vms.append({
                "vmid": vmid,
                "name": str(item.get("name") or f"VM {vmid}"),
                "node": str(item.get("node") or ""),
                "status": str(item.get("status") or "unknown"),
                "template": bool(item.get("template")),
            })
        vms.sort(key=lambda x: (not x["template"], x["name"].lower(), x["vmid"]))

        try:
            next_vmid = int(next_payload.get("data"))
        except (TypeError, ValueError):
            next_vmid = 100

        default_node = nodes[0] if nodes else ""
        node_options = self.node_install_options(
            profile=profile,
            environment=environment,
            api_user=api_user,
            token_name=token_name,
            token_secret=token_secret,
            settings=settings,
            node=default_node,
        ) if default_node else {
            "node": "", "image_storages": [], "iso_storages": [], "isos": [], "bridges": ["vmbr0"]
        }

        return {
            "next_vmid": next_vmid,
            "nodes": nodes,
            "vms": vms,
            "default_node": default_node,
            "node_options": node_options,
        }

    def node_install_options(
        self,
        *,
        profile: UserProfile,
        environment: Environment,
        api_user: str,
        token_name: str,
        token_secret: str,
        settings: AppSettings,
        node: str,
    ) -> dict[str, Any]:
        if profile.role != Role.ADMIN:
            raise PermissionError("Somente o Administrador do laboratório pode consultar opções de provisionamento.")
        node = validate_identifier(node, "node")

        def req(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            return self._request(
                profile_id=profile.id or 0,
                environment=environment,
                api_user=api_user,
                token_name=token_name,
                token_secret=token_secret,
                settings=settings,
                method="GET",
                path=path,
                params=params,
            )

        image_payload = req(f"/nodes/{node}/storage", {"content": "images", "enabled": 1})
        iso_storage_payload = req(f"/nodes/{node}/storage", {"content": "iso", "enabled": 1})
        network_payload = req(f"/nodes/{node}/network")

        def storage_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
            rows = []
            for item in payload.get("data") or []:
                storage = str(item.get("storage") or "").strip()
                if not storage:
                    continue
                if item.get("enabled") in (0, False) or item.get("active") in (0, False):
                    continue
                rows.append({
                    "storage": storage,
                    "type": str(item.get("type") or ""),
                    "content": str(item.get("content") or ""),
                    "avail": item.get("avail"),
                    "total": item.get("total"),
                    "shared": bool(item.get("shared")),
                })
            return rows

        image_storages = storage_rows(image_payload)
        iso_storages = storage_rows(iso_storage_payload)

        isos: list[dict[str, Any]] = []
        for storage in iso_storages:
            sid = validate_identifier(storage["storage"], "storage")
            try:
                content_payload = req(
                    f"/nodes/{node}/storage/{sid}/content",
                    {"content": "iso"},
                )
            except Exception:
                continue
            for item in content_payload.get("data") or []:
                volid = str(item.get("volid") or "").strip()
                if not volid:
                    continue
                isos.append({
                    "volid": volid,
                    "storage": sid,
                    "size": item.get("size"),
                    "format": item.get("format"),
                })
        isos.sort(key=lambda x: x["volid"].lower())

        bridges = []
        for item in network_payload.get("data") or []:
            iface = str(item.get("iface") or "").strip()
            kind = str(item.get("type") or "").lower()
            if iface and (kind in {"bridge", "ovsbridge", "any_bridge"} or iface.startswith("vmbr")):
                bridges.append(iface)
        bridges = sorted(set(bridges)) or ["vmbr0"]

        return {
            "node": node,
            "image_storages": image_storages,
            "iso_storages": iso_storages,
            "isos": isos,
            "bridges": bridges,
        }

    def query_iso_url(
        self,
        *,
        profile: UserProfile,
        environment: Environment,
        api_user: str,
        token_name: str,
        token_secret: str,
        settings: AppSettings,
        node: str,
        url: str,
        verify_certificates: bool = True,
    ) -> dict[str, Any]:
        if profile.role != Role.ADMIN:
            raise PermissionError("Somente o Administrador do laboratório pode consultar URLs a partir do nó Proxmox.")
        node = validate_identifier(node, "node")
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Informe uma URL HTTP ou HTTPS válida.")
        if len(url) > 4096:
            raise ValueError("URL muito longa.")
        payload = self._request(
            profile_id=profile.id or 0,
            environment=environment,
            api_user=api_user,
            token_name=token_name,
            token_secret=token_secret,
            settings=settings,
            method="GET",
            path=f"/nodes/{node}/query-url-metadata",
            params={"url": url.strip(), "verify-certificates": 1 if verify_certificates else 0},
        )
        return payload.get("data") or {}

    def download_iso(
        self,
        *,
        profile: UserProfile,
        environment: Environment,
        api_user: str,
        token_name: str,
        token_secret: str,
        settings: AppSettings,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        if profile.role != Role.ADMIN:
            raise PermissionError("Somente o Administrador do laboratório pode baixar ISOs pelo Proxmox.")
        if not bool(data.get("confirmed")):
            raise PermissionError("O download exige confirmação explícita.")
        node = validate_identifier(str(data.get("node") or ""), "node")
        storage = validate_identifier(str(data.get("storage") or ""), "storage")
        url = str(data.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Informe uma URL HTTP ou HTTPS válida.")
        filename = str(data.get("filename") or "").strip()
        filename = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", filename):
            raise ValueError("Nome de arquivo ISO inválido.")
        if not filename.lower().endswith((".iso", ".img")):
            raise ValueError("O arquivo precisa terminar em .iso ou .img.")

        request_data: dict[str, Any] = {
            "content": "iso",
            "url": url,
            "filename": filename,
            "verify-certificates": 1 if bool(data.get("verify_certificates", True)) else 0,
        }
        checksum = str(data.get("checksum") or "").strip().lower()
        checksum_algorithm = str(data.get("checksum_algorithm") or "").strip().lower()
        if checksum or checksum_algorithm:
            allowed = {"md5", "sha1", "sha224", "sha256", "sha384", "sha512"}
            if checksum_algorithm not in allowed:
                raise ValueError("Algoritmo de checksum inválido.")
            if not re.fullmatch(r"[0-9a-fA-F]{16,128}", checksum):
                raise ValueError("Checksum inválido.")
            request_data["checksum"] = checksum
            request_data["checksum-algorithm"] = checksum_algorithm

        payload = self._request(
            profile_id=profile.id or 0,
            environment=environment,
            api_user=api_user,
            token_name=token_name,
            token_secret=token_secret,
            settings=settings,
            method="POST",
            path=f"/nodes/{node}/storage/{storage}/download-url",
            data=request_data,
        )
        task_id = payload.get("data")
        self.audit.log(
            "proxmox", "download_iso", profile.display_name,
            target=f"{storage}:iso/{filename}",
            details={"node": node, "url": url, "task_id": task_id},
        )
        return {"ok": True, "task_id": task_id, "volid": f"{storage}:iso/{filename}"}

    def task_status(
        self,
        *,
        profile: UserProfile,
        environment: Environment,
        api_user: str,
        token_name: str,
        token_secret: str,
        settings: AppSettings,
        node: str,
        upid: str,
    ) -> dict[str, Any]:
        if not permissions_for(profile).proxmox_read:
            raise PermissionError("Perfil sem permissão para consultar tasks do Proxmox.")
        node = validate_identifier(node, "node")
        if not upid or len(upid) > 2048:
            raise ValueError("UPID inválido.")
        payload = self._request(
            profile_id=profile.id or 0,
            environment=environment,
            api_user=api_user,
            token_name=token_name,
            token_secret=token_secret,
            settings=settings,
            method="GET",
            path=f"/nodes/{node}/tasks/{quote(upid, safe='')}/status",
        )
        return payload.get("data") or {}

    def clone_vm(
        self,
        *,
        profile: UserProfile,
        environment: Environment,
        api_user: str,
        token_name: str,
        token_secret: str,
        settings: AppSettings,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        if profile.role != Role.ADMIN:
            raise PermissionError("Somente o Administrador do laboratório pode clonar VMs/templates.")
        if not bool(data.get("confirmed")):
            raise PermissionError("A clonagem exige confirmação explícita.")
        source_node = validate_identifier(str(data.get("source_node") or ""), "node de origem")
        target_node = validate_identifier(str(data.get("node") or ""), "node de destino")
        storage = validate_identifier(str(data.get("storage") or ""), "storage")
        try:
            source_vmid = int(data.get("source_vmid"))
            newid = int(data.get("vmid"))
        except (TypeError, ValueError) as exc:
            raise ValueError("VMID de origem e destino precisam ser inteiros.") from exc
        name = str(data.get("name") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}", name):
            raise ValueError("Nome da VM inválido.")
        payload = self._request(
            profile_id=profile.id or 0,
            environment=environment,
            api_user=api_user,
            token_name=token_name,
            token_secret=token_secret,
            settings=settings,
            method="POST",
            path=f"/nodes/{source_node}/qemu/{source_vmid}/clone",
            data={
                "newid": newid,
                "name": name,
                "target": target_node,
                "storage": storage,
                "full": 1,
            },
        )
        task_id = payload.get("data")
        self.audit.log(
            "proxmox", "clone_vm", profile.display_name, target=str(newid),
            details={"source_vmid": source_vmid, "source_node": source_node, "node": target_node, "storage": storage, "task_id": task_id},
        )
        return {"ok": True, "vmid": newid, "name": name, "node": target_node, "task_id": task_id}

    def open_web_forward(
        self,
        *,
        profile: UserProfile,
        environment: Environment,
        api_user: str,
        token_name: str,
        token_secret: str,
        settings: AppSettings,
    ) -> dict[str, Any]:
        if not permissions_for(profile).proxmox_read:
            raise PermissionError("Perfil sem permissão para acessar o Proxmox.")
        # Exigimos que a integração Proxmox esteja configurada, mas o token é
        # usado apenas pela API nativa. A Web UI continua usando sessão/ticket.
        self._headers(api_user, token_name, token_secret)
        old = self._web_forwards.pop(profile.id or 0, None)
        if old:
            try:
                self.ssh.close_forward(profile.id or 0, old["forward_id"])
            except Exception:
                pass
        forward = self.ssh.open_forward(
            profile.id or 0,
            environment.proxmox_internal_host,
            environment.proxmox_port,
        )
        self._web_forwards[profile.id or 0] = forward
        return {
            "url": f"https://127.0.0.1:{forward['local_port']}/",
            "local_port": forward["local_port"],
            "forward_id": forward["forward_id"],
            "note": "O API Token não autentica a Web UI. O painel Web solicitará um login Proxmox normal.",
        }

    def power_action(
        self,
        *,
        profile: UserProfile,
        environment: Environment,
        api_user: str,
        token_name: str,
        token_secret: str,
        settings: AppSettings,
        vmid: int,
        node: str,
        vm_type: str,
        action: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        if not confirmed:
            raise PermissionError("A ação exige confirmação explícita.")
        perms = permissions_for(profile)
        if not perms.proxmox_power:
            raise PermissionError("Perfil sem permissão para ligar/desligar VMs.")
        assert_vm_allowed(profile, vmid)
        if action not in {"start", "stop", "reboot"}:
            raise ValueError("Ação Proxmox não permitida.")
        node = validate_identifier(node, "node")
        if vm_type not in {"qemu", "lxc"}:
            raise ValueError("Tipo de VM/CT inválido.")
        payload = self._request(
            profile_id=profile.id or 0,
            environment=environment,
            api_user=api_user,
            token_name=token_name,
            token_secret=token_secret,
            settings=settings,
            method="POST",
            path=f"/nodes/{node}/{vm_type}/{vmid}/status/{action}",
        )
        task_id = payload.get("data")
        self.audit.log(
            "proxmox",
            action,
            profile.display_name,
            target=str(vmid),
            details={"node": node, "type": vm_type, "task_id": task_id},
        )
        return {"ok": True, "task_id": task_id}
