from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PORT = 8765
PORT_RANGE = range(8765, 8800)
BIND_HOST = "127.0.0.1"
_HELD_LOCKS: set[Path] = set()


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

    def acquire(self) -> LockAcquireResult:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        existing = self._read_lock()
        reclaimed_stale = False
        if existing:
            running_pid = int(existing.get("pid", 0))
            if self.lock_path in _HELD_LOCKS or _pid_is_alive(running_pid):
                return LockAcquireResult(False, self.lock_path, running_pid=running_pid)
            reclaimed_stale = True

        payload = {
            "pid": self.pid,
            "host": self.host,
            "port": self.port,
            "started_at": time.time(),
            "fingerprint": f"{self.pid}:{self.host}:{self.port}",
        }
        self.lock_path.write_text(json.dumps(payload, sort_keys=True))
        _HELD_LOCKS.add(self.lock_path)
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
            "handshake_nonce": os.urandom(12).hex(),
        }
        self.port_path.write_text(json.dumps(payload, sort_keys=True))
        if project_root is not None:
            project_runtime = Path(project_root) / ".hydralab" / "runtime"
            project_runtime.mkdir(parents=True, exist_ok=True)
            (project_runtime / "backend.json").write_text(json.dumps(payload, sort_keys=True))
        return payload

    def release(self) -> None:
        _HELD_LOCKS.discard(self.lock_path)
        for path in (self.lock_path, self.port_path):
            if path.exists():
                path.unlink()

    def _read_lock(self) -> dict | None:
        if not self.lock_path.exists():
            return None
        try:
            return json.loads(self.lock_path.read_text())
        except json.JSONDecodeError:
            return None


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
