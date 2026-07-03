"""Packaged-app updater primitives.

The Phase 3 updater is inert in source/dev mode. This package owns only the
testable contracts and release-build guardrails; native packaging remains a
documented scaffold until real Apple signing/notarization credentials exist.
"""

from hydra.updater.activity import GitOperationTracker, WriteOperationTracker
from hydra.updater.flow import UpdateCheckResult, UpdaterSettings
from hydra.updater.guard import ActiveWorkGuard, ActiveWorkStatus

__all__ = [
    "ActiveWorkGuard",
    "ActiveWorkStatus",
    "GitOperationTracker",
    "UpdateCheckResult",
    "UpdaterSettings",
    "WriteOperationTracker",
]
