from __future__ import annotations

from contextlib import contextmanager
from threading import RLock
from typing import Iterator


class OperationTracker:
    """Small in-process counter for update-install blockers."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._count = 0

    @property
    def active(self) -> bool:
        with self._lock:
            return self._count > 0

    def begin(self) -> None:
        with self._lock:
            self._count += 1

    def end(self) -> None:
        with self._lock:
            if self._count <= 0:
                raise RuntimeError("operation tracker end() called without a matching begin()")
            self._count -= 1

    @contextmanager
    def track(self) -> Iterator[None]:
        self.begin()
        try:
            yield
        finally:
            self.end()


class GitOperationTracker(OperationTracker):
    pass


class WriteOperationTracker(OperationTracker):
    pass


DEFAULT_GIT_OPERATION_TRACKER = GitOperationTracker()
DEFAULT_WRITE_OPERATION_TRACKER = WriteOperationTracker()
