"""Persistência SQLite para metadados não secretos."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from pibic_lab_core.domain.models import AppSettings, Environment, InstallationJob, UserProfile


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()
        self._seed_defaults()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS environments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    gateway_host TEXT NOT NULL,
                    ssh_port INTEGER NOT NULL,
                    proxmox_internal_host TEXT NOT NULL,
                    proxmox_port INTEGER NOT NULL,
                    zerotier_network_id TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    ssh_username TEXT NOT NULL DEFAULT '',
                    assigned_vmids TEXT NOT NULL DEFAULT '[]',
                    can_proxmox_power INTEGER NOT NULL DEFAULT 0,
                    can_install_services INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ssh_preferences (
                    profile_id INTEGER PRIMARY KEY,
                    auth_method TEXT NOT NULL DEFAULT 'agent',
                    key_path TEXT NOT NULL DEFAULT '',
                    save_password INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS proxmox_preferences (
                    profile_id INTEGER PRIMARY KEY,
                    api_user TEXT NOT NULL DEFAULT '',
                    token_name TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS app_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS installation_jobs (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS detected_services (
                    profile_id INTEGER NOT NULL,
                    service_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY(profile_id, service_id)
                );
                """
            )

    def _seed_defaults(self) -> None:
        with self._lock, self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM environments").fetchone()["n"]
            if count == 0:
                conn.execute(
                    """INSERT INTO environments
                    (name, gateway_host, ssh_port, proxmox_internal_host, proxmox_port, zerotier_network_id, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, 1)""",
                    ("Laboratório PIBIC / UNIR", "10.57.144.217", 22, "10.99.0.59", 8006, ""),
                )
            count = conn.execute("SELECT COUNT(*) AS n FROM profiles").fetchone()["n"]
            if count == 0:
                profile = UserProfile()
                cursor = conn.execute(
                    """INSERT INTO profiles
                    (display_name, role, ssh_username, assigned_vmids, can_proxmox_power,
                     can_install_services, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        profile.display_name,
                        profile.role.value,
                        profile.ssh_username,
                        json.dumps(profile.assigned_vmids),
                        int(profile.can_proxmox_power),
                        int(profile.can_install_services),
                        profile.created_at,
                    ),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO ssh_preferences(profile_id, auth_method, key_path, save_password) VALUES (?, 'agent', '', 0)",
                    (cursor.lastrowid,),
                )
            row = conn.execute("SELECT id FROM app_settings WHERE id=1").fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO app_settings(id, payload) VALUES (1, ?)",
                    (AppSettings().model_dump_json(),),
                )

    # Environments -----------------------------------------------------------------
    def list_environments(self) -> list[Environment]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM environments WHERE enabled=1 ORDER BY id").fetchall()
        return [Environment(**dict(row)) for row in rows]

    def get_environment(self, env_id: int) -> Environment:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM environments WHERE id=?", (env_id,)).fetchone()
        if not row:
            raise ValueError("Ambiente não encontrado")
        return Environment(**dict(row))

    def save_environment(self, environment: Environment) -> Environment:
        with self._lock, self._connect() as conn:
            if environment.id:
                conn.execute(
                    """UPDATE environments SET name=?, gateway_host=?, ssh_port=?,
                    proxmox_internal_host=?, proxmox_port=?, zerotier_network_id=?, enabled=?
                    WHERE id=?""",
                    (
                        environment.name,
                        environment.gateway_host,
                        environment.ssh_port,
                        environment.proxmox_internal_host,
                        environment.proxmox_port,
                        environment.zerotier_network_id,
                        int(environment.enabled),
                        environment.id,
                    ),
                )
                return environment
            cursor = conn.execute(
                """INSERT INTO environments(name,gateway_host,ssh_port,proxmox_internal_host,
                proxmox_port,zerotier_network_id,enabled) VALUES (?,?,?,?,?,?,?)""",
                (
                    environment.name,
                    environment.gateway_host,
                    environment.ssh_port,
                    environment.proxmox_internal_host,
                    environment.proxmox_port,
                    environment.zerotier_network_id,
                    int(environment.enabled),
                ),
            )
            environment.id = int(cursor.lastrowid)
            return environment

    # Profiles ---------------------------------------------------------------------
    def list_profiles(self) -> list[UserProfile]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM profiles ORDER BY id").fetchall()
        return [self._profile_from_row(row) for row in rows]

    def get_profile(self, profile_id: int) -> UserProfile:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        if not row:
            raise ValueError("Perfil não encontrado")
        return self._profile_from_row(row)

    @staticmethod
    def _profile_from_row(row: sqlite3.Row) -> UserProfile:
        data = dict(row)
        data["assigned_vmids"] = json.loads(data.get("assigned_vmids") or "[]")
        data["can_proxmox_power"] = bool(data["can_proxmox_power"])
        data["can_install_services"] = bool(data["can_install_services"])
        return UserProfile(**data)

    def save_profile(self, profile: UserProfile) -> UserProfile:
        with self._lock, self._connect() as conn:
            values = (
                profile.display_name,
                profile.role.value,
                profile.ssh_username,
                json.dumps(profile.assigned_vmids),
                int(profile.can_proxmox_power),
                int(profile.can_install_services),
                profile.created_at,
            )
            if profile.id:
                conn.execute(
                    """UPDATE profiles SET display_name=?, role=?, ssh_username=?, assigned_vmids=?,
                    can_proxmox_power=?, can_install_services=?, created_at=? WHERE id=?""",
                    values + (profile.id,),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO ssh_preferences(profile_id, auth_method, key_path, save_password) VALUES (?, 'agent', '', 0)",
                    (profile.id,),
                )
                return profile
            cursor = conn.execute(
                """INSERT INTO profiles(display_name,role,ssh_username,assigned_vmids,
                can_proxmox_power,can_install_services,created_at) VALUES (?,?,?,?,?,?,?)""",
                values,
            )
            profile.id = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO ssh_preferences(profile_id, auth_method, key_path, save_password) VALUES (?, 'agent', '', 0)",
                (profile.id,),
            )
            return profile

    def get_ssh_preferences(self, profile_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ssh_preferences WHERE profile_id=?", (profile_id,)).fetchone()
        if not row:
            return {"profile_id": profile_id, "auth_method": "agent", "key_path": "", "save_password": False}
        data = dict(row)
        data["save_password"] = bool(data["save_password"])
        return data

    def save_ssh_preferences(self, profile_id: int, auth_method: str, key_path: str, save_password: bool) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO ssh_preferences(profile_id,auth_method,key_path,save_password)
                VALUES (?,?,?,?) ON CONFLICT(profile_id) DO UPDATE SET
                auth_method=excluded.auth_method,key_path=excluded.key_path,save_password=excluded.save_password""",
                (profile_id, auth_method, key_path, int(save_password)),
            )

    def get_proxmox_preferences(self, profile_id: int) -> dict[str, str]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM proxmox_preferences WHERE profile_id=?", (profile_id,)).fetchone()
        return dict(row) if row else {"profile_id": profile_id, "api_user": "", "token_name": ""}

    def save_proxmox_preferences(self, profile_id: int, api_user: str, token_name: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO proxmox_preferences(profile_id,api_user,token_name) VALUES (?,?,?)
                ON CONFLICT(profile_id) DO UPDATE SET api_user=excluded.api_user, token_name=excluded.token_name""",
                (profile_id, api_user, token_name),
            )

    # Settings ---------------------------------------------------------------------
    def get_settings(self) -> AppSettings:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM app_settings WHERE id=1").fetchone()
        return AppSettings.model_validate_json(row["payload"] if row else AppSettings().model_dump_json())

    def save_settings(self, settings: AppSettings) -> AppSettings:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO app_settings(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (settings.model_dump_json(),),
            )
        return settings

    # Jobs -------------------------------------------------------------------------
    def save_job(self, job: InstallationJob) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO installation_jobs(id,payload) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (job.id, job.model_dump_json()),
            )

    def list_jobs(self, limit: int = 50) -> list[InstallationJob]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM installation_jobs ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        return [InstallationJob.model_validate_json(row["payload"]) for row in rows]

    def save_detected_service(self, profile_id: int, service_id: str, payload: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO detected_services(profile_id, service_id, payload) VALUES (?,?,?)
                ON CONFLICT(profile_id,service_id) DO UPDATE SET payload=excluded.payload""",
                (profile_id, service_id, payload),
            )
