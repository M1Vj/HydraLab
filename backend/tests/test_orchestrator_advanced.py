"""Phase-3 advanced orchestrator customization tests."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.contracts import RunStatus
from hydra.agents.policy import FULL_ACCESS, TRUST_UNTRUSTED
from hydra.agents.runs import RunRepository
from hydra.autonomy.loop import AutopilotLoop
from hydra.autonomy.policy import AutonomyPolicy, BudgetLimits
from hydra.database.models import AgentAuditLedgerEntry, AgentRun, AgentRunCandidate, ReviewItem
from hydra.orchestrator.advanced import (
    ADVANCED_RUN_PRESETS,
    AdvancedConfigValidationError,
    AdvancedRunConfig,
    CandidateStore,
    build_advanced_run_config,
    route_untrusted_advanced_preset,
)
from hydra.orchestrator.run import RunConfig, RunExecutionResult


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


def test_hl_mode_20_21_presets_expand_losslessly_to_advanced_config():
    for preset_id, preset in ADVANCED_RUN_PRESETS.items():
        config = build_advanced_run_config(preset_id=preset_id)

        assert config.model_dump() == preset.model_dump()
        assert set(config.model_dump()) == {
            "candidate_count",
            "population_size",
            "compare_enabled",
            "ranking_method",
            "review_depth",
            "evolution_method",
            "validation_rules",
            "max_loop_iterations",
            "stop_conditions",
            "budget_policy",
            "checkpoint_frequency",
        }


def test_hl_mode_22_invalid_population_size_returns_field_and_allowed_range():
    with pytest.raises(AdvancedConfigValidationError) as err:
        build_advanced_run_config(overrides={"population_size": 1_001})

    assert err.value.field == "population_size"
    assert err.value.allowed == "1..100"
    assert "population_size" in str(err.value)


def test_hl_mode_24_unknown_ranking_method_returns_allowed_set():
    with pytest.raises(AdvancedConfigValidationError) as err:
        build_advanced_run_config(overrides={"ranking_method": "bracket"})

    assert err.value.field == "ranking_method"
    assert err.value.allowed == "elo, pairwise, rubric, tournament"


def test_hl_safe_08_validation_rules_are_fixed_allowlist_only():
    with pytest.raises(AdvancedConfigValidationError) as err:
        build_advanced_run_config(overrides={"validation_rules": ["pytest -q"]})

    assert err.value.field == "validation_rules"
    assert err.value.allowed == "build, lint, test, typecheck"


@pytest.mark.asyncio
async def test_hl_mode_23_candidate_store_round_trips_ranked_artifacts(session):
    run = await RunRepository(session).create_run(project_id="default", mode=FULL_ACCESS)
    config = build_advanced_run_config(overrides={"ranking_method": "tournament"})
    rows = await CandidateStore(session).store_ranked_candidates(
        run_id=run.id,
        project_id="default",
        ranking_method=config.ranking_method,
        candidates=[
            {"id": "draft-a", "title": "A", "score": 0.81, "body": "candidate A"},
            {"id": "draft-b", "title": "B", "score": 0.64, "body": "candidate B"},
        ],
    )

    assert len(rows) == 2
    reopened = (await session.exec(select(AgentRunCandidate).where(AgentRunCandidate.run_id == run.id))).all()
    assert [row.candidate_id for row in reopened] == ["draft-a", "draft-b"]
    assert [row.ranking_score for row in reopened] == [0.81, 0.64]
    assert {row.ranking_method for row in reopened} == {"tournament"}
    assert json.loads(reopened[0].candidate_artifact_json)["body"] == "candidate A"


@pytest.mark.asyncio
async def test_hl_mode_24_advanced_ranking_method_records_compare_audit(session):
    config = build_advanced_run_config(overrides={"ranking_method": "elo"})
    result = await RunStateMachineWithAdvanced(session, config).start()

    audit = (await session.exec(select(AgentAuditLedgerEntry))).all()
    assert result.state == "completed"
    assert any(row.action == "compare.ranking_method" and row.target == "elo" for row in audit)


@pytest.mark.asyncio
async def test_hl_mode_25_advanced_loop_ceiling_blocks_and_prompts(session):
    async def fake_start(*, project_id, mode, recipe="autopilot-loop", inputs=None, data=None):
        run = await RunRepository(session).create_run(project_id=project_id, mode=mode, recipe=recipe, inputs=inputs)
        await RunRepository(session).complete_run(run.id)
        return RunExecutionResult(run_id=run.id, state="completed")

    class FakeRunner:
        start = staticmethod(fake_start)

    config = build_advanced_run_config(overrides={"max_loop_iterations": 1})
    loop = AutopilotLoop(
        session,
        _policy(config),
        config.to_run_config(),
        runner_factory=lambda repo, run_config, budget: FakeRunner(),  # type: ignore[return-value]
    )

    result = await loop.start(project_id="default")

    run = await session.get(AgentRun, result.run_id)
    assert run.status == RunStatus.BLOCKED.value
    assert run.stop_reason == "max_loop_iterations"
    trace = await RunRepository(session).get_trace(run.id)
    assert trace.steps[-1].kind == "loop_control.blocked"
    assert "continue, raise the ceiling, or stop" in trace.steps[-1].summary


@pytest.mark.asyncio
async def test_hl_mode_26_advanced_config_cannot_disable_policy_exclusions(session):
    config = build_advanced_run_config()

    result = await config.governed_action(
        session,
        mode=FULL_ACCESS,
        action_kind="provider_routing",
        target_ref="settings.toml",
        full_access_enabled=True,
    )

    assert result.applied is False
    assert result.status in {"approval_required", "review_inbox"}


@pytest.mark.asyncio
async def test_hl_trust_10_untrusted_advanced_preset_routes_to_review_inbox(session):
    config = build_advanced_run_config(overrides={"ranking_method": "rubric"})

    item = await route_untrusted_advanced_preset(
        session,
        project_id="default",
        config=config,
        provenance=TRUST_UNTRUSTED,
        origin_id="browser-event-1",
    )

    runs = (await session.exec(select(AgentRun))).all()
    review_items = (await session.exec(select(ReviewItem))).all()
    assert runs == []
    assert review_items[0].id == item["id"]
    assert review_items[0].item_type == "advanced-run-config-preset"
    assert json.loads(review_items[0].payload_json)["trust_origin"] == TRUST_UNTRUSTED


class RunStateMachineWithAdvanced:
    def __init__(self, session: AsyncSession, config: AdvancedRunConfig) -> None:
        from hydra.orchestrator.run import RunStateMachine

        self.session = session
        self.config = config
        self.machine = RunStateMachine(RunRepository(session), config.to_run_config())

    async def start(self):
        return await self.machine.start(project_id="default", mode=FULL_ACCESS)


def _policy(config: AdvancedRunConfig) -> AutonomyPolicy:
    return AutonomyPolicy(
        mode=FULL_ACCESS,
        budget_limits=BudgetLimits(
            tokens=config.budget_policy.tokens,
            wall_clock_seconds=config.budget_policy.wall_clock_seconds,
        ),
        max_loop_count=config.max_loop_iterations,
        stop_conditions=config.stop_conditions,
        checkpoint_required=True,
        approval_required=True,
        autopilot_enabled=True,
    )
