"""Compute-backend model surface (HL-SAFE-10).

The SQLModel tables live in the canonical ``hydra.database.models`` registry so
the Alembic ``create_all`` marker and ``init_db`` pick them up everywhere; this
module re-exports them at the guide's import path plus the resource-limit
helpers the registry and sandbox share.
"""

from __future__ import annotations

from dataclasses import dataclass

from hydra.database.models import ComputeBackend

LOCAL_SANDBOX = "local_sandbox"
CLOUD = "cloud"
BACKEND_KINDS = (LOCAL_SANDBOX, CLOUD)


@dataclass(frozen=True)
class ResourceLimits:
    cpu_seconds: int = 5
    memory_bytes: int = 512 * 1024 * 1024
    wall_clock_seconds: int = 10
    log_cap_bytes: int = 1024 * 1024

    def as_dict(self) -> dict[str, int]:
        return {
            "cpu_seconds": self.cpu_seconds,
            "memory_bytes": self.memory_bytes,
            "wall_clock_seconds": self.wall_clock_seconds,
            "log_cap_bytes": self.log_cap_bytes,
        }


DEFAULT_LOCAL_LIMITS = ResourceLimits()

__all__ = ["ComputeBackend", "ResourceLimits", "DEFAULT_LOCAL_LIMITS", "LOCAL_SANDBOX", "CLOUD", "BACKEND_KINDS"]
