from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SidecarConflictResult:
    record: dict[str, Any]
    used_mtime: bool = False
    conflict: bool = False


def resolve_sidecar_conflict(left: dict[str, Any], right: dict[str, Any]) -> SidecarConflictResult:
    if left["sidecar_record_id"] != right["sidecar_record_id"]:
        raise ValueError("sidecar conflict requires the same sidecar_record_id")
    if int(left.get("rev", 0)) > int(right.get("rev", 0)):
        return SidecarConflictResult(record=left)
    if int(right.get("rev", 0)) > int(left.get("rev", 0)):
        return SidecarConflictResult(record=right)
    if left.get("content_hash") == right.get("content_hash"):
        return SidecarConflictResult(record=left)
    return SidecarConflictResult(record=left, conflict=True)


def external_edit_forces_reindex(stored_hash: str, sidecar_hash: str, app_wrote_last: bool) -> bool:
    return stored_hash != sidecar_hash and not app_wrote_last
