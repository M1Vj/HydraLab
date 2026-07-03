import json
import os
import socket
import stat
import subprocess
import sys
from multiprocessing import Event, Process, Queue
from pathlib import Path

import pytest

from hydra.storage.runtime import BackendRuntime, choose_available_port, choose_bind_host
from hydra.storage import runtime as runtime_module


def _dead_process_fingerprint() -> tuple[int, str | None]:
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.05)"])
    pid = proc.pid
    fingerprint = BackendRuntime.process_fingerprint(pid)
    proc.wait(timeout=5)
    return pid, fingerprint


def _hold_runtime_lock_with_stale_payload(app_data_root: str, ready: Queue, release: Event) -> None:
    runtime = BackendRuntime(app_data_root=Path(app_data_root), port=8765)
    result = runtime.acquire()
    runtime.lock_path.write_text(
        json.dumps(
            {
                "pid": 999_999_999,
                "host": "127.0.0.1",
                "port": 8765,
                "fingerprint": "dead-process",
            },
            sort_keys=True,
        )
    )
    ready.put({"acquired": result.acquired, "pid": os.getpid()})
    release.wait(timeout=10)
    runtime.release()


def test_hl_core_08_lock_is_cross_process_and_released(tmp_path):
    ready: Queue = Queue()
    release = Event()
    holder = Process(target=_hold_runtime_lock_with_stale_payload, args=(str(tmp_path), ready, release))
    holder.start()
    try:
        acquired = ready.get(timeout=5)
        assert acquired["acquired"] is True

        contender = BackendRuntime(app_data_root=tmp_path, port=8765)
        blocked = contender.acquire()

        assert blocked.acquired is False
        assert blocked.running_pid is not None
    finally:
        release.set()
        holder.join(timeout=5)
        if holder.is_alive():
            holder.terminate()
            holder.join(timeout=5)

    runtime_after_release = BackendRuntime(app_data_root=tmp_path, port=8765)
    after_release = runtime_after_release.acquire()
    assert after_release.acquired is True
    runtime_after_release.release()


def test_hl_core_08_dead_pid_lock_is_reclaimed(tmp_path):
    dead_pid, fingerprint = _dead_process_fingerprint()
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "hydralab-backend.lock").write_text(
        json.dumps(
            {
                "pid": dead_pid,
                "host": "127.0.0.1",
                "port": 8765,
                "fingerprint": fingerprint,
            },
            sort_keys=True,
        )
    )

    runtime = BackendRuntime(app_data_root=tmp_path, port=8765)
    result = runtime.acquire()

    assert result.acquired is True
    assert result.reclaimed_stale is True
    runtime.release()


def test_hl_core_08_failed_contender_release_does_not_remove_owner_lock(tmp_path):
    owner = BackendRuntime(app_data_root=tmp_path, port=8765)
    assert owner.acquire().acquired is True

    contender = BackendRuntime(app_data_root=tmp_path, port=8765)
    assert contender.acquire().acquired is False
    contender.release()

    assert owner.lock_path.exists()
    still_blocked = BackendRuntime(app_data_root=tmp_path, port=8765).acquire()
    assert still_blocked.acquired is False

    owner.release()


def test_hl_core_08_port_selection_falls_back_when_default_is_bound():
    # Bind whatever port the selector currently prefers rather than hardcoding
    # 8765, so the test is deterministic even when a real HydraLab backend (or any
    # other process) already holds the default port.
    first = choose_available_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        occupied.bind((choose_bind_host(), first))
        occupied.listen(1)

        fallback = choose_available_port()

    assert fallback != first
    assert fallback > first


def test_hl_core_08_port_files_are_owner_only_and_removed(tmp_path):
    app_data = tmp_path / "app-data"
    project = tmp_path / "project"
    runtime = BackendRuntime(app_data_root=app_data, port=8765)
    assert runtime.acquire().acquired is True

    payload = runtime.write_port_file(project_root=project)

    app_file = app_data / "runtime" / "backend.json"
    project_file = project / ".hydralab" / "runtime" / "backend.json"
    assert json.loads(app_file.read_text()) == payload
    assert json.loads(project_file.read_text()) == payload
    assert "token" not in app_file.read_text().lower()
    if sys.platform != "win32":
        # POSIX mode bits are meaningless on Windows (chmod is a no-op there);
        # owner-only protection relies on the per-user profile ACL instead.
        assert stat.S_IMODE(app_file.stat().st_mode) == 0o600
        assert stat.S_IMODE(project_file.stat().st_mode) == 0o600

    runtime.release()
    assert not app_file.exists()
    assert not project_file.exists()


def test_hl_core_08_lifespan_writes_and_removes_runtime_files(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("HYDRA_HOME", str(tmp_path / "db"))
    monkeypatch.setenv("HYDRALAB_APP_DATA_ROOT", str(tmp_path / "app-data"))
    monkeypatch.setenv("HYDRALAB_PROJECT_ROOT", str(tmp_path / "project"))
    monkeypatch.setenv("HYDRALAB_PORT", "8765")

    from hydra.app import create_app

    with TestClient(create_app()) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert (tmp_path / "app-data" / "runtime" / "backend.json").exists()
        assert (tmp_path / "project" / ".hydralab" / "runtime" / "backend.json").exists()

    assert not (tmp_path / "app-data" / "runtime" / "backend.json").exists()
    assert not (tmp_path / "project" / ".hydralab" / "runtime" / "backend.json").exists()

def test_windows_lock_helper_uses_msvcrt_when_fcntl_unavailable(tmp_path, monkeypatch):
    calls: list[tuple[int, int]] = []

    class FakeMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        @staticmethod
        def locking(_fileno: int, mode: int, size: int) -> None:
            calls.append((mode, size))

    monkeypatch.setattr(runtime_module, "fcntl", None)
    monkeypatch.setattr(runtime_module, "msvcrt", FakeMsvcrt)

    lock_path = tmp_path / "runtime.lock"
    with lock_path.open("a+") as handle:
        runtime_module._lock_file_exclusive(handle)
        runtime_module._unlock_file(handle)

    assert calls == [(FakeMsvcrt.LK_NBLCK, 1), (FakeMsvcrt.LK_UNLCK, 1)]

class _FakeCFunc:
    """Stand-in for a WinDLL function: callable, and accepts restype/argtypes."""

    def __init__(self, fn):
        self._fn = fn
        self.restype = None
        self.argtypes = None

    def __call__(self, *args):
        return self._fn(*args)


def test_windows_process_fingerprint_uses_ctypes_without_crashing(monkeypatch):
    class FakeFiletime:
        def __init__(self) -> None:
            self.dwLowDateTime = 0
            self.dwHighDateTime = 0

    class FakeKernel32:
        def __init__(self) -> None:
            self.OpenProcess = _FakeCFunc(lambda _access, _inherit, _pid: 100)
            self.CloseHandle = _FakeCFunc(lambda _handle: None)

            def _times(_handle, creation, _exit, _kernel, _user):
                creation.dwLowDateTime = 7
                creation.dwHighDateTime = 3
                return 1

            self.GetProcessTimes = _FakeCFunc(_times)

    class FakeCtypes:
        c_void_p = int
        c_int = int
        c_uint32 = int

        class wintypes:
            FILETIME = FakeFiletime

        @staticmethod
        def WinDLL(_name: str, use_last_error: bool = False):
            return FakeKernel32()

        @staticmethod
        def byref(value):
            return value

    monkeypatch.setattr(runtime_module.sys, "platform", "win32")
    monkeypatch.setattr(runtime_module, "_pid_is_alive", lambda _pid: True)
    monkeypatch.setattr(runtime_module, "ctypes", FakeCtypes)

    assert runtime_module.process_fingerprint(os.getpid()) == f"win32-ctime:{(3 << 32) + 7}"


def test_windows_pid_is_alive_uses_waitforsingleobject(monkeypatch):
    WAIT_TIMEOUT = 0x00000102

    def make_ctypes(open_handle: int, wait_result: int, last_error: int = 0):
        class FakeKernel32:
            def __init__(self) -> None:
                self.OpenProcess = _FakeCFunc(lambda _a, _i, _p: open_handle)
                self.WaitForSingleObject = _FakeCFunc(lambda _h, _ms: wait_result)
                self.CloseHandle = _FakeCFunc(lambda _h: None)

        class FakeCtypes:
            c_void_p = int
            c_int = int
            c_uint32 = int

            @staticmethod
            def WinDLL(_name: str, use_last_error: bool = False):
                return FakeKernel32()

            @staticmethod
            def get_last_error():
                return last_error

        return FakeCtypes

    monkeypatch.setattr(runtime_module.sys, "platform", "win32")

    # Running process: handle opens, wait times out (not signalled) -> alive.
    monkeypatch.setattr(runtime_module, "ctypes", make_ctypes(77, WAIT_TIMEOUT))
    assert runtime_module._pid_is_alive(123) is True

    # Exited process: handle opens, wait returns signalled (0) -> not alive.
    monkeypatch.setattr(runtime_module, "ctypes", make_ctypes(77, 0))
    assert runtime_module._pid_is_alive(123) is False

    # No handle + ACCESS_DENIED (5) means the process exists but is inaccessible.
    monkeypatch.setattr(runtime_module, "ctypes", make_ctypes(0, 0, last_error=5))
    assert runtime_module._pid_is_alive(123) is True

    # No handle + invalid-parameter (87) means no such process.
    monkeypatch.setattr(runtime_module, "ctypes", make_ctypes(0, 0, last_error=87))
    assert runtime_module._pid_is_alive(123) is False

def test_posix_process_fingerprint_still_returns_value_or_none():
    fingerprint = runtime_module.process_fingerprint(os.getpid())
    assert fingerprint is None or isinstance(fingerprint, str)
