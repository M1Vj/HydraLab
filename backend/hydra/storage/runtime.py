from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fcntl


DEFAULT_PORT = 8765
PORT_RANGE = range(8765, 8800)
BIND_HOST = "127.0.0.1"


@dataclass(frozen=True)
class LockAcquireResult:
    acquired: bool
    lock_path: Path
    running_pid: int | None = None
    reclaimed_stale: bool = False


def choose_bind_host() -> str:
    return BIND_HOST


class BackendRuntime:
    def __init__(self, app_data_root: Path, pid: int | None = None, host: str = BIND_HOST, port: int = DEFAULT_PORT) -> None:
        if host != BIND_HOST:
            raise ValueError("HydraLab backend may bind 127.0.0.1 only")
        self.app_data_root = Path(app_data_root)
        self.pid = pid or os.getpid()
        self.host = host
        self.port = port
        self.runtime_dir = self.app_data_root / "runtime"
        self.lock_path = self.runtime_dir / "hydralab-backend.lock"
        self.port_path = self.runtime_dir / "backend.json"
        self._lock_file: Any | None = None
        self._port_files: set[Path] = {self.port_path}

    def acquire(self) -> LockAcquireResult:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.chmod(0o700)
        lock_file = self.lock_path.open("a+")
        os.chmod(self.lock_path, 0o600)
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            existing = self._read_lock_from_file(lock_file)
            lock_file.close()
            return LockAcquireResult(
                False,
                self.lock_path,
                running_pid=_payload_pid(existing),
                reclaimed_stale=False,
            )

        existing = self._read_lock()
        reclaimed_stale = False
        if existing:
            running_pid = _payload_pid(existing)
            fingerprint = existing.get("fingerprint")
            live_fingerprint = self.process_fingerprint(running_pid) if running_pid else None
            if running_pid != self.pid and live_fingerprint and live_fingerprint == fingerprint:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
                return LockAcquireResult(False, self.lock_path, running_pid=running_pid)
            reclaimed_stale = True

        payload = {
            "pid": self.pid,
            "host": self.host,
            "port": self.port,
            "started_at": time.time(),
            "fingerprint": self.process_fingerprint(self.pid),
        }
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(json.dumps(payload, sort_keys=True))
        lock_file.flush()
        os.fsync(lock_file.fileno())
        self._lock_file = lock_file
        return LockAcquireResult(True, self.lock_path, reclaimed_stale=reclaimed_stale)

    def write_port_file(self, project_root: Path | None = None) -> dict:
        payload = {
            "pid": self.pid,
            "host": self.host,
            "port": self.port,
            "scheme": "http",
            "base_url": f"http://{self.host}:{self.port}",
            "api_version": "v1",
            "started_at": time.time(),
            "health_url": f"http://{self.host}:{self.port}/healthz",
        }
        _write_owner_only_json(self.port_path, payload)
        self._port_files.add(self.port_path)
        if project_root is not None:
            project_runtime = Path(project_root) / ".hydralab" / "runtime"
            project_runtime.mkdir(parents=True, exist_ok=True)
            project_runtime.chmod(0o700)
            project_port_path = project_runtime / "backend.json"
            _write_owner_only_json(project_port_path, payload)
            self._port_files.add(project_port_path)
        return payload

    def release(self) -> None:
        for path in tuple(self._port_files):
            if path.exists():
                path.unlink()
        if self._lock_file is not None:
            try:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            finally:
                self._lock_file.close()
                self._lock_file = None
        if self.lock_path.exists():
            self.lock_path.unlink()

    def _read_lock(self) -> dict | None:
        if not self.lock_path.exists():
            return None
        try:
            return json.loads(self.lock_path.read_text())
        except json.JSONDecodeError:
            return None

    def _read_lock_from_file(self, lock_file: Any) -> dict | None:
        try:
            lock_file.seek(0)
            raw = lock_file.read()
            return json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return None

    @staticmethod
    def process_fingerprint(pid: int) -> str | None:
        return process_fingerprint(pid)


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def choose_available_port(host: str = BIND_HOST, ports: range = PORT_RANGE) -> int:
    if host != BIND_HOST:
        raise ValueError("HydraLab backend may bind 127.0.0.1 only")
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError("no free local port in HydraLab backend range 8765-8799")


def process_fingerprint(pid: int) -> str | None:
    if not _pid_is_alive(pid):
        return None
    proc_stat = Path(f"/proc/{pid}/stat")
    if proc_stat.exists():
        try:
            fields = proc_stat.read_text().split()
            return f"linux-starttime:{fields[21]}"
        except (IndexError, OSError):
            pass
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    started_at = result.stdout.strip()
    return f"ps-lstart:{started_at}" if result.returncode == 0 and started_at else None


def _payload_pid(payload: dict | None) -> int | None:
    if not payload:
        return None
    try:
        pid = int(payload.get("pid", 0))
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _write_owner_only_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.chmod(path, 0o600)
