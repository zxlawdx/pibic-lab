"""SSH assíncrono, host-key verification, PTY e port forwarding."""
from __future__ import annotations

import asyncio
import base64
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import asyncssh

from pibic_lab_core.domain.models import AuthMethod, HostKeyInfo, SSHConnectionConfig
from pibic_lab_core.security.hostkeys import find_host_key_line, replace_host_key
from pibic_lab_core.util.async_runtime import AsyncLoopRunner


@dataclass
class TerminalState:
    id: str
    process: Any
    created_at: float = field(default_factory=time.time)
    buffer: bytearray = field(default_factory=bytearray)
    closed: bool = False
    exit_status: int | None = None
    reader_tasks: list[asyncio.Task] = field(default_factory=list)


@dataclass
class SSHState:
    profile_id: int
    config: SSHConnectionConfig
    conn: Any
    connected_at: float = field(default_factory=time.time)
    terminals: dict[str, TerminalState] = field(default_factory=dict)
    forwards: dict[str, Any] = field(default_factory=dict)


class SSHSessionManager:
    MAX_TERMINAL_BUFFER = 2 * 1024 * 1024

    def __init__(self, known_hosts_path: Path) -> None:
        self.known_hosts_path = known_hosts_path
        self.known_hosts_path.parent.mkdir(parents=True, exist_ok=True)
        self.known_hosts_path.touch(exist_ok=True)
        self.runner = AsyncLoopRunner()
        self._states: dict[int, SSHState] = {}

    # Host key ---------------------------------------------------------------------
    def probe_host_key(self, host: str, port: int = 22) -> HostKeyInfo:
        return self.runner.run(self._probe_host_key(host, port), timeout=15)

    async def _probe_host_key(
        self,
        host: str,
        port: int,
    ) -> HostKeyInfo:
        try:
            key = await asyncio.wait_for(
                asyncssh.get_server_host_key(
                    host,
                    port=port,
                ),
                timeout=8,
            )

            if key is None:
                raise RuntimeError(
                    "Servidor não apresentou uma host key SSH."
                )

            public_key = (
                key.export_public_key("openssh")
                .decode("utf-8")
                .strip()
            )

            stored = find_host_key_line(
                self.known_hosts_path,
                host,
                port,
            )

            current_material = public_key
            stored_material = None

            if stored:
                parts = stored.split(maxsplit=1)

                stored_material = (
                    parts[1].strip()
                    if len(parts) == 2
                    else ""
                )

            return HostKeyInfo(
                host=host,
                port=port,
                algorithm=key.get_algorithm(),
                fingerprint_sha256=key.get_fingerprint("sha256"),
                public_key=public_key,
                trusted=bool(
                    stored
                    and stored_material == current_material
                ),
                changed=bool(
                    stored
                    and stored_material != current_material
                ),
            )

        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"Tempo limite excedido ao tentar acessar "
                f"{host}:{port}. Verifique o ZeroTier, o gateway "
                f"e a porta SSH."
            ) from exc

        except OSError as exc:
            raise RuntimeError(
                f"Não foi possível acessar o servidor SSH "
                f"{host}:{port}: {exc}"
            ) from exc

        except asyncssh.Error as exc:
            raise RuntimeError(
                f"Erro SSH ao consultar a host key de "
                f"{host}:{port}: {exc}"
            ) from exc
    def trust_host_key(self, info: HostKeyInfo) -> None:
        replace_host_key(self.known_hosts_path, info.host, info.port, info.public_key)

    # Connection -------------------------------------------------------------------
    def connect(
        self,
        profile_id: int,
        config: SSHConnectionConfig,
        *,
        password: str | None = None,
        key_passphrase: str | None = None,
    ) -> dict[str, Any]:
        return self.runner.run(
            self._connect(profile_id, config, password=password, key_passphrase=key_passphrase),
            timeout=25,
        )

    async def _connect(
        self,
        profile_id: int,
        config: SSHConnectionConfig,
        *,
        password: str | None,
        key_passphrase: str | None,
    ) -> dict[str, Any]:
        if profile_id in self._states:
            await self._disconnect(profile_id)

        kwargs: dict[str, Any] = {
            "host": config.host,
            "port": config.port,
            "username": config.username,
            "known_hosts": str(self.known_hosts_path),
            "connect_timeout": 12,
            "keepalive_interval": 20,
            "keepalive_count_max": 3,
        }

        if config.auth_method == AuthMethod.PASSWORD:
            if not password:
                raise ValueError("Senha SSH não informada.")
            # Quando o usuário escolhe senha, não tente agent/chaves por baixo dos panos.
            kwargs.update(
                password=password,
                client_keys=None,
                agent_path=None,
                public_key_auth=False,
            )
        elif config.auth_method == AuthMethod.KEY:
            # O método "arquivo de chave" deve usar somente o arquivo selecionado.
            kwargs["agent_path"] = None
            if not config.key_path:
                raise ValueError("Caminho da chave SSH não informado.")
            key_path = Path(config.key_path).expanduser()
            if not key_path.exists():
                raise FileNotFoundError(f"Chave SSH não encontrada: {key_path}")
            if key_passphrase:
                key = asyncssh.read_private_key(str(key_path), passphrase=key_passphrase)
                kwargs["client_keys"] = [key]
            else:
                kwargs["client_keys"] = [str(key_path)]
        else:
            # Sem client_keys explícito, o AsyncSSH consulta SSH_AUTH_SOCK e, em seguida,
            # as chaves padrão ~/.ssh/id_* sem copiar uma chave privada para o app.
            pass

        conn = await asyncssh.connect(**kwargs)
        state = SSHState(profile_id=profile_id, config=config, conn=conn)
        self._states[profile_id] = state
        return {
            "connected": True,
            "profile_id": profile_id,
            "host": config.host,
            "port": config.port,
            "username": config.username,
            "server_version": str(conn.get_extra_info("server_version", "") or ""),
        }

    def disconnect(self, profile_id: int) -> None:
        self.runner.run(self._disconnect(profile_id), timeout=12)

    async def _disconnect(self, profile_id: int) -> None:
        state = self._states.pop(profile_id, None)
        if not state:
            return
        for terminal_id in list(state.terminals):
            await self._close_terminal_state(state, terminal_id)
        for listener in list(state.forwards.values()):
            listener.close()
            try:
                await listener.wait_closed()
            except Exception:
                pass
        state.forwards.clear()
        state.conn.close()
        try:
            await state.conn.wait_closed()
        except Exception:
            pass

    def is_connected(self, profile_id: int) -> bool:
        state = self._states.get(profile_id)
        return bool(state and not state.conn.is_closed())

    def status(self, profile_id: int) -> dict[str, Any]:
        return self.runner.run(self._status(profile_id), timeout=5)

    async def _status(self, profile_id: int) -> dict[str, Any]:
        state = self._states.get(profile_id)
        if not state or state.conn.is_closed():
            return {"connected": False, "profile_id": profile_id}
        return {
            "connected": True,
            "profile_id": profile_id,
            "host": state.config.host,
            "port": state.config.port,
            "username": state.config.username,
            "connected_for": int(time.time() - state.connected_at),
            "terminal_count": len(state.terminals),
            "forward_count": len(state.forwards),
        }

    def _require_state(self, profile_id: int) -> SSHState:
        state = self._states.get(profile_id)
        if not state or state.conn.is_closed():
            raise RuntimeError("Sessão SSH não está conectada.")
        return state

    # Fixed command execution -------------------------------------------------------
    def run_command(self, profile_id: int, command: str, timeout: int = 15) -> dict[str, Any]:
        return self.runner.run(self._run_command(profile_id, command, timeout), timeout=timeout + 5)

    async def _run_command(self, profile_id: int, command: str, timeout: int) -> dict[str, Any]:
        state = self._require_state(profile_id)
        result = await asyncio.wait_for(state.conn.run(command, check=False), timeout=timeout)
        return {
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "exit_status": result.exit_status,
        }

    def run_command_with_stdin(
        self, profile_id: int, command: str, stdin_data: bytes, timeout: int = 30
    ) -> dict[str, Any]:
        return self.runner.run(
            self._run_command_with_stdin(profile_id, command, stdin_data, timeout),
            timeout=timeout + 5,
        )

    async def _run_command_with_stdin(
        self, profile_id: int, command: str, stdin_data: bytes, timeout: int
    ) -> dict[str, Any]:
        state = self._require_state(profile_id)
        if len(stdin_data) > 64 * 1024:
            raise ValueError("Entrada para comando muito grande.")
        process = await state.conn.create_process(command, encoding=None)
        process.stdin.write(stdin_data)
        process.stdin.write_eof()
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                process.terminate()
            except Exception:
                pass
            raise
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return {
            "stdout": stdout or "",
            "stderr": stderr or "",
            "exit_status": process.exit_status,
        }

    def run_command_with_pty_stdin(
        self,
        profile_id: int,
        command: str,
        stdin_data: bytes,
        timeout: int = 30,
    ) -> dict[str, Any]:
        return self.runner.run(
            self._run_command_with_pty_stdin(
                profile_id,
                command,
                stdin_data,
                timeout,
            ),
            timeout=timeout + 5,
        )

    async def _run_command_with_pty_stdin(
        self,
        profile_id: int,
        command: str,
        stdin_data: bytes,
        timeout: int,
    ) -> dict[str, Any]:
        state = self._require_state(profile_id)

        if len(stdin_data) > 64 * 1024:
            raise ValueError("Entrada para comando muito grande.")

        process = await state.conn.create_process(
            command,
            term_type="xterm-256color",
            term_size=(120, 40),
            encoding=None,
        )

        # doas solicita a senha através de um terminal.
        # Damos tempo para ele criar o prompt antes de enviar.
        await asyncio.sleep(0.25)
        process.stdin.write(stdin_data)

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            try:
                process.terminate()
            except Exception:
                pass
            raise

        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")

        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")

        # Garante que a senha nunca apareça no retorno/log,
        # mesmo que algum terminal remoto a tenha ecoado.
        password = stdin_data.decode("utf-8", errors="ignore").strip()

        if password:
            stdout = (stdout or "").replace(password, "[REDACTED]")
            stderr = (stderr or "").replace(password, "[REDACTED]")

        return {
            "stdout": stdout or "",
            "stderr": stderr or "",
            "exit_status": process.exit_status,
        }

    # Terminal ----------------------------------------------------------------------
    def open_terminal(self, profile_id: int, cols: int = 100, rows: int = 30) -> dict[str, Any]:
        return self.runner.run(self._open_terminal(profile_id, cols, rows), timeout=15)

    async def _open_terminal(self, profile_id: int, cols: int, rows: int) -> dict[str, Any]:
        state = self._require_state(profile_id)
        process = await state.conn.create_process(
            term_type="xterm-256color",
            term_size=(max(20, cols), max(5, rows)),
            encoding=None,
        )
        terminal_id = uuid.uuid4().hex
        terminal = TerminalState(id=terminal_id, process=process)
        state.terminals[terminal_id] = terminal
        terminal.reader_tasks = [
            asyncio.create_task(self._reader(terminal, process.stdout)),
            asyncio.create_task(self._reader(terminal, process.stderr)),
            asyncio.create_task(self._watch_process(terminal)),
        ]
        return {"session_id": terminal_id, "opened": True}

    async def _reader(self, terminal: TerminalState, stream: Any) -> None:
        try:
            while True:
                chunk = await stream.read(8192)
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8", errors="replace")
                terminal.buffer.extend(chunk)
                overflow = len(terminal.buffer) - self.MAX_TERMINAL_BUFFER
                if overflow > 0:
                    del terminal.buffer[:overflow]
        except (asyncio.CancelledError, Exception):
            return

    async def _watch_process(self, terminal: TerminalState) -> None:
        try:
            await terminal.process.wait_closed()
        except Exception:
            pass
        terminal.closed = True
        try:
            terminal.exit_status = terminal.process.exit_status
        except Exception:
            terminal.exit_status = None

    def terminal_input(self, profile_id: int, terminal_id: str, data_b64: str) -> None:
        self.runner.run(self._terminal_input(profile_id, terminal_id, data_b64), timeout=5)

    async def _terminal_input(self, profile_id: int, terminal_id: str, data_b64: str) -> None:
        state = self._require_state(profile_id)
        terminal = state.terminals.get(terminal_id)
        if not terminal or terminal.closed:
            raise RuntimeError("Terminal não está ativo.")
        raw = base64.b64decode(data_b64, validate=True)
        if len(raw) > 64 * 1024:
            raise ValueError("Entrada de terminal muito grande.")
        terminal.process.stdin.write(raw)
        drain = getattr(terminal.process.stdin, "drain", None)
        if drain:
            await drain()

    def terminal_resize(self, profile_id: int, terminal_id: str, cols: int, rows: int) -> None:
        self.runner.run(self._terminal_resize(profile_id, terminal_id, cols, rows), timeout=5)

    async def _terminal_resize(self, profile_id: int, terminal_id: str, cols: int, rows: int) -> None:
        state = self._require_state(profile_id)
        terminal = state.terminals.get(terminal_id)
        if not terminal or terminal.closed:
            return
        cols = max(20, min(int(cols), 500))
        rows = max(5, min(int(rows), 200))
        changer = getattr(terminal.process, "change_terminal_size", None)
        if changer:
            changer(cols, rows)
        elif getattr(terminal.process, "channel", None):
            terminal.process.channel.change_terminal_size(cols, rows)

    def terminal_poll(self, profile_id: int, terminal_id: str) -> dict[str, Any]:
        return self.runner.run(self._terminal_poll(profile_id, terminal_id), timeout=5)

    async def _terminal_poll(self, profile_id: int, terminal_id: str) -> dict[str, Any]:
        state = self._require_state(profile_id)
        terminal = state.terminals.get(terminal_id)
        if not terminal:
            return {"closed": True, "data_b64": "", "exit_status": None}
        data = bytes(terminal.buffer)
        terminal.buffer.clear()
        return {
            "closed": terminal.closed,
            "data_b64": base64.b64encode(data).decode("ascii") if data else "",
            "exit_status": terminal.exit_status,
        }

    def close_terminal(self, profile_id: int, terminal_id: str) -> None:
        self.runner.run(self._close_terminal(profile_id, terminal_id), timeout=8)

    async def _close_terminal(self, profile_id: int, terminal_id: str) -> None:
        state = self._require_state(profile_id)
        await self._close_terminal_state(state, terminal_id)

    async def _close_terminal_state(self, state: SSHState, terminal_id: str) -> None:
        terminal = state.terminals.pop(terminal_id, None)
        if not terminal:
            return
        try:
            terminal.process.stdin.write_eof()
        except Exception:
            pass
        try:
            terminal.process.terminate()
        except Exception:
            pass
        for task in terminal.reader_tasks:
            if not task.done():
                task.cancel()
        terminal.closed = True

    # Forwarding --------------------------------------------------------------------
    def open_forward(self, profile_id: int, remote_host: str, remote_port: int) -> dict[str, Any]:
        return self.runner.run(self._open_forward(profile_id, remote_host, remote_port), timeout=10)

    async def _open_forward(self, profile_id: int, remote_host: str, remote_port: int) -> dict[str, Any]:
        state = self._require_state(profile_id)
        # remote_host vem do cadastro administrativo do ambiente, não da linha de comando do usuário.
        listener = await state.conn.forward_local_port("127.0.0.1", 0, remote_host, remote_port)
        forward_id = uuid.uuid4().hex
        state.forwards[forward_id] = listener
        return {"forward_id": forward_id, "local_host": "127.0.0.1", "local_port": listener.get_port()}

    def open_socks(self, profile_id: int) -> dict[str, Any]:
        return self.runner.run(self._open_socks(profile_id), timeout=10)

    async def _open_socks(self, profile_id: int) -> dict[str, Any]:
        state = self._require_state(profile_id)
        listener = await state.conn.forward_socks("127.0.0.1", 0)
        forward_id = uuid.uuid4().hex
        state.forwards[forward_id] = listener
        return {
            "forward_id": forward_id,
            "local_host": "127.0.0.1",
            "local_port": listener.get_port(),
            "kind": "socks5",
        }

    def close_forward(self, profile_id: int, forward_id: str) -> None:
        self.runner.run(self._close_forward(profile_id, forward_id), timeout=8)

    async def _close_forward(self, profile_id: int, forward_id: str) -> None:
        state = self._require_state(profile_id)
        listener = state.forwards.pop(forward_id, None)

        if not listener:
            return

        listener.close()

        # O fechamento do listener não pode invalidar uma requisição
        # Proxmox que já terminou corretamente.
        try:
            await asyncio.wait_for(
                listener.wait_closed(),
                timeout=1.5,
            )
        except (asyncio.TimeoutError, Exception):
            pass
