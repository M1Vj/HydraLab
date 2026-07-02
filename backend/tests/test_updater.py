from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import AgentModePolicy, AgentRun, ExperimentRun, IngestionJob, ProviderSettings, Source
from hydra.settings.toml_config import SettingsValidationError, default_settings, validate_settings
from hydra.updater.activity import GitOperationTracker, WriteOperationTracker
from hydra.updater.flow import (
    apply_update_without_policy,
    check_for_updates,
    install_update,
    read_updater_settings,
    write_updater_settings,
)
from hydra.updater.guard import ActiveWorkGuard
from hydra.updater.rollback import VersionReference, restore_previous_version_after_failed_install


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine):
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get(self, url: str) -> dict[str, str]:
        self.calls.append(url)
        return {"ok": "true"}


async def _add_agent_run(session: AsyncSession, status: str) -> None:
    session.add(AgentRun(project_id="default", status=status))
    await session.commit()


async def _add_ingestion_job(session: AsyncSession, status: str) -> None:
    source = Source(project_id="default", title="Paper")
    session.add(source)
    await session.commit()
    await session.refresh(source)
    session.add(IngestionJob(source_id=source.id, source_path="sources/paper.pdf", status=status))
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["running", "queued"])
async def test_active_work_guard_blocks_running_or_queued_agent_runs(session, status):
    await _add_agent_run(session, status)
    guard = ActiveWorkGuard(git_tracker=GitOperationTracker(), write_tracker=WriteOperationTracker())

    result = await guard.check(session, "default")

    assert result.active is True
    assert result.reasons == ("agent_run",)


async def _add_experiment_run(session: AsyncSession, status: str) -> None:
    session.add(ExperimentRun(project_id="default", status=status))
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["running", "paused", "pending", "awaiting_approval"])
async def test_active_work_guard_blocks_live_experiment_runs(session, status):
    await _add_experiment_run(session, status)
    guard = ActiveWorkGuard(git_tracker=GitOperationTracker(), write_tracker=WriteOperationTracker())

    result = await guard.check(session, "default")

    assert result.active is True
    assert result.reasons == ("experiment_run",)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled", "killed:timeout"])
async def test_active_work_guard_ignores_terminal_experiment_runs(session, status):
    await _add_experiment_run(session, status)
    guard = ActiveWorkGuard(git_tracker=GitOperationTracker(), write_tracker=WriteOperationTracker())

    result = await guard.check(session, "default")

    assert result.active is False
    assert "experiment_run" not in result.reasons


@pytest.mark.asyncio
async def test_active_work_guard_blocks_running_document_conversion(session):
    await _add_ingestion_job(session, "running")
    guard = ActiveWorkGuard(git_tracker=GitOperationTracker(), write_tracker=WriteOperationTracker())

    result = await guard.check(session, "default")

    assert result.active is True
    assert result.reasons == ("conversion",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tracker_name", "expected"),
    [("git", "git_operation"), ("write", "write_operation")],
)
async def test_active_work_guard_blocks_in_memory_operations(session, tracker_name, expected):
    git_tracker = GitOperationTracker()
    write_tracker = WriteOperationTracker()
    tracker = git_tracker if tracker_name == "git" else write_tracker
    guard = ActiveWorkGuard(git_tracker=git_tracker, write_tracker=write_tracker)

    with tracker.track():
        result = await guard.check(session, "default")

    assert result.active is True
    assert result.reasons == (expected,)


@pytest.mark.asyncio
async def test_active_work_guard_allows_install_when_idle(session):
    guard = ActiveWorkGuard(git_tracker=GitOperationTracker(), write_tracker=WriteOperationTracker())

    result = await install_update(session, guard=guard, project_id="default")

    assert result.status == "ready_to_install"
    assert result.active_work.active is False


@pytest.mark.asyncio
async def test_install_update_defers_when_active_work_exists(session):
    await _add_agent_run(session, "running")
    guard = ActiveWorkGuard(git_tracker=GitOperationTracker(), write_tracker=WriteOperationTracker())

    result = await install_update(session, guard=guard, project_id="default")

    assert result.status == "deferred"
    assert result.active_work.includes("agent_run")


def test_updater_channel_settings_round_trip_and_reject_invalid_values():
    settings = default_settings()

    for channel in ("stable", "preview", "dev"):
        write_updater_settings(settings, channel=channel)
        validate_settings(settings)
        assert read_updater_settings(settings).channel == channel

    settings["updater"]["channel"] = "nightly"
    with pytest.raises(SettingsValidationError, match=r"\[updater\]\.channel"):
        validate_settings(settings)


def test_updater_auto_check_toggle_round_trips():
    settings = default_settings()

    write_updater_settings(settings, auto_check_enabled=False)

    validate_settings(settings)
    assert read_updater_settings(settings).auto_check_enabled is False


def test_failed_install_restores_previous_launchable_version():
    result = restore_previous_version_after_failed_install(
        failed_installer=VersionReference("1.5.0", "/tmp/HydraLab-1.5.0.dmg"),
        previous_version=VersionReference("1.4.0", "/tmp/HydraLab-1.4.0.dmg", launchable=True),
    )

    assert result.active_version == "1.4.0"
    assert result.launchable is True
    assert result.retained_failed_installer == "/tmp/HydraLab-1.5.0.dmg"


@pytest.mark.asyncio
async def test_disable_auto_check_stops_packaged_network_check():
    settings = default_settings()
    write_updater_settings(settings, auto_check_enabled=False)
    client = FakeHttpClient()

    result = await check_for_updates(settings, client, packaged_build=True)

    assert result.attempted is False
    assert result.reason == "auto-check disabled"
    assert client.calls == []


@pytest.mark.asyncio
async def test_packaged_auto_check_attempts_network_when_enabled():
    settings = default_settings()
    write_updater_settings(settings, channel="preview", auto_check_enabled=True)
    client = FakeHttpClient()

    result = await check_for_updates(settings, client, packaged_build=True)

    assert result.attempted is True
    assert result.channel == "preview"
    assert len(client.calls) == 1
    assert "/preview/" in client.calls[0]


@pytest.mark.asyncio
async def test_auto_update_is_inert_in_source_dev_mode_by_default():
    settings = default_settings()
    client = FakeHttpClient()

    result = await check_for_updates(settings, client)

    assert result.attempted is False
    assert result.reason == "source/dev mode"
    assert client.calls == []


def _json_table(rows: list[object]) -> str:
    return json.dumps([row.model_dump(mode="json") for row in rows], sort_keys=True)


@pytest.mark.asyncio
async def test_update_apply_without_policy_never_mutates_provider_policy_or_settings(session):
    settings = default_settings()
    settings["providers"] = {"routing_policy": "manual", "accounts": {"openai": {"secret_ref": "keychain:openai"}}}
    settings["skills"] = {"enabled": ["summarize-paper"], "capabilities": {"summarize-paper": ["read"]}}
    settings["assistant"]["mode"] = "passive"
    before_settings = json.dumps(
        {key: settings[key] for key in ("providers", "skills", "assistant")},
        sort_keys=True,
    )
    session.add(ProviderSettings(provider="openai", model="gpt-4.1", secret_ref="keychain:openai"))
    session.add(AgentModePolicy(project_id="default", default_mode="passive", autonomy_policy_json='{"skills":[]}' ))
    await session.commit()
    before_providers = _json_table((await session.exec(select(ProviderSettings))).all())
    before_policies = _json_table((await session.exec(select(AgentModePolicy))).all())

    result = await apply_update_without_policy(session, settings)

    assert result == "policy_not_authorized"
    assert _json_table((await session.exec(select(ProviderSettings))).all()) == before_providers
    assert _json_table((await session.exec(select(AgentModePolicy))).all()) == before_policies
    assert json.dumps({key: settings[key] for key in ("providers", "skills", "assistant")}, sort_keys=True) == before_settings
