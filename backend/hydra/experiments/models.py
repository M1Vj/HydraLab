"""Experiment-run model surface (HL-SAFE-13/14).

Re-exports the canonical SQLModel tables plus the run status vocabulary. The
tables themselves live in ``hydra.database.models`` so every create_all path
registers them.
"""

from __future__ import annotations

from hydra.database.models import ExperimentExecutionSetting, ExperimentRun, ExperimentRunLog

# Non-terminal + terminal statuses. ``killed:<reason>`` values are written
# verbatim; the reasons below enumerate the ones this subsystem emits.
STATUS_PENDING = "pending"
STATUS_AWAITING_APPROVAL = "awaiting_approval"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

KILLED_TIMEOUT = "killed:timeout"
KILLED_NETWORK = "killed:network"
KILLED_PATH_ESCAPE = "killed:path_escape"
KILLED_CPU = "killed:cpu"
KILLED_MEMORY = "killed:memory"

TERMINAL_STATUSES = frozenset(
    {
        STATUS_SUCCEEDED,
        STATUS_FAILED,
        STATUS_CANCELLED,
        KILLED_TIMEOUT,
        KILLED_NETWORK,
        KILLED_PATH_ESCAPE,
        KILLED_CPU,
        KILLED_MEMORY,
    }
)


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES or status.startswith("killed:")


__all__ = [
    "ExperimentRun",
    "ExperimentRunLog",
    "ExperimentExecutionSetting",
    "STATUS_PENDING",
    "STATUS_AWAITING_APPROVAL",
    "STATUS_RUNNING",
    "STATUS_PAUSED",
    "STATUS_SUCCEEDED",
    "STATUS_FAILED",
    "STATUS_CANCELLED",
    "KILLED_TIMEOUT",
    "KILLED_NETWORK",
    "KILLED_PATH_ESCAPE",
    "KILLED_CPU",
    "KILLED_MEMORY",
    "TERMINAL_STATUSES",
    "is_terminal",
]
