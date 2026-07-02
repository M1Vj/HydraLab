from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VersionReference:
    version: str
    artifact_path: str
    launchable: bool = True


@dataclass(frozen=True)
class RollbackResult:
    active_version: str
    launchable: bool
    retained_failed_installer: str
    restored_from: str


def restore_previous_version_after_failed_install(
    *,
    failed_installer: VersionReference,
    previous_version: VersionReference,
) -> RollbackResult:
    if not previous_version.launchable:
        raise ValueError("previous version is not launchable")
    return RollbackResult(
        active_version=previous_version.version,
        launchable=True,
        retained_failed_installer=failed_installer.artifact_path,
        restored_from=previous_version.artifact_path,
    )
