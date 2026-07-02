from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from typing import Any, Protocol

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.settings.toml_config import VALID_UPDATE_CHANNELS, SettingsValidationError
from hydra.updater.guard import ActiveWorkGuard, ActiveWorkStatus

PACKAGED_BUILD_ENV = "HYDRALAB_PACKAGED_BUILD"


class AsyncHttpClient(Protocol):
    async def get(self, url: str) -> Any: ...


@dataclass(frozen=True)
class UpdaterSettings:
    channel: str = "stable"
    auto_check_enabled: bool = True


@dataclass(frozen=True)
class UpdateCheckResult:
    attempted: bool
    channel: str
    response: Any = None
    reason: str = ""


@dataclass(frozen=True)
class InstallResult:
    status: str
    active_work: ActiveWorkStatus


def packaged_build_enabled() -> bool:
    return os.environ.get(PACKAGED_BUILD_ENV) == "1"


def read_updater_settings(settings: dict[str, Any]) -> UpdaterSettings:
    section = settings.get("updater", {})
    channel = str(section.get("channel", "stable"))
    if channel not in VALID_UPDATE_CHANNELS:
        allowed = ", ".join(VALID_UPDATE_CHANNELS)
        raise SettingsValidationError(f"[updater].channel must be one of {allowed}; got {channel!r}")
    return UpdaterSettings(
        channel=channel,
        auto_check_enabled=bool(section.get("auto_check_enabled", True)),
    )


def write_updater_settings(
    settings: dict[str, Any],
    *,
    channel: str | None = None,
    auto_check_enabled: bool | None = None,
) -> dict[str, Any]:
    section = settings.setdefault("updater", {})
    if channel is not None:
        if channel not in VALID_UPDATE_CHANNELS:
            allowed = ", ".join(VALID_UPDATE_CHANNELS)
            raise SettingsValidationError(f"[updater].channel must be one of {allowed}; got {channel!r}")
        section["channel"] = channel
    if auto_check_enabled is not None:
        section["auto_check_enabled"] = bool(auto_check_enabled)
    return settings


def _updater_target() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def _updater_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "aarch64"
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    return machine or "x86_64"


def updater_current_version() -> str:
    try:
        from importlib.metadata import version

        return version("hydra-research-assistant")
    except Exception:
        return "0.0.0"


def channel_feed_url(channel: str) -> str:
    if channel not in VALID_UPDATE_CHANNELS:
        allowed = ", ".join(VALID_UPDATE_CHANNELS)
        raise SettingsValidationError(f"Update channel must be one of {allowed}; got {channel!r}")
    # Substitute the Tauri-style placeholders: this URL is fetched server-side by
    # httpx, which (unlike the Tauri updater plugin) does not expand {{target}} /
    # {{arch}} / {{current_version}}, so a literal-brace URL would never resolve.
    return (
        f"https://updates.hydralab.local/{channel}/"
        f"{_updater_target()}/{_updater_arch()}/{updater_current_version()}"
    )


async def check_for_updates(
    settings: dict[str, Any],
    http_client: AsyncHttpClient,
    *,
    packaged_build: bool | None = None,
    manual: bool = False,
) -> UpdateCheckResult:
    updater = read_updater_settings(settings)
    if packaged_build is None:
        packaged_build = packaged_build_enabled()
    if not packaged_build:
        return UpdateCheckResult(False, updater.channel, reason="source/dev mode")
    if not manual and not updater.auto_check_enabled:
        return UpdateCheckResult(False, updater.channel, reason="auto-check disabled")
    response = await http_client.get(channel_feed_url(updater.channel))
    return UpdateCheckResult(True, updater.channel, response=response)


async def install_update(
    session: AsyncSession,
    *,
    project_id: str = "default",
    guard: ActiveWorkGuard | None = None,
) -> InstallResult:
    guard = guard or ActiveWorkGuard()
    active_work = await guard.check(session, project_id)
    if active_work.active:
        return InstallResult(status="deferred", active_work=active_work)
    return InstallResult(status="ready_to_install", active_work=active_work)


async def apply_update_without_policy(session: AsyncSession, settings: dict[str, Any]) -> str:
    """Documented no-op: binary updates never mutate protected policy/settings."""

    _ = (session, settings)
    return "policy_not_authorized"
