"""Phase-2 bounded orchestrator stage-engine tests.

Covers the backend-testable @HL-* scenarios in
`.agents/features/02-assistant-co-scientist/03-orchestrator-stage-engine.md`.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.policy import FULL_ACCESS, PASSIVE, Outcome
from hydra.agents.runs import RunBudget, RunRepository
from hydra.database.models import AgentRun
from hydra.orchestrator.dispatch import DispatchAction, DispatchGuard, PrivacyPosture
from hydra.orchestrator.run import RunConfig, RunStateMachine
from hydra.orchestrator.stages import CompareStage, StageEnum, StageResult


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


def test_hl_mode_10_stage_enum_has_exactly_seven_canonical_members():
    assert [stage.value for stage in StageEnum] == [
        "generate",
        "review",
        "compare",
        "evolve",
        "validate",
        "cache",
        "loop_control",
    ]
    assert "robin" not in [stage.value for stage in StageEnum]
    assert "co_scientist" not in [stage.value for stage in StageEnum]
    assert "alphaproof" not in [stage.value for stage in StageEnum]


def test_hl_mode_12_19_run_config_resolves_toggles_and_rejects_phase3_looping():
    config = RunConfig.resolve(
        global_enabled={"generate": True, "review": True, "compare": True},
        stage_overrides={"compare": False},
    )

    assert config.enabled_stages == {
        StageEnum.GENERATE: True,
        StageEnum.REVIEW: True,
        StageEnum.COMPARE: False,
        StageEnum.EVOLVE: False,
        StageEnum.VALIDATE: False,
        StageEnum.CACHE: False,
        StageEnum.LOOP_CONTROL: False,
    }

    next_run = RunConfig.resolve(global_enabled={"generate": True, "review": True, "compare": True})
    assert next_run.enabled_stages[StageEnum.COMPARE] is True

    with pytest.raises(ValueError, match="loop_count"):
        RunConfig.resolve(loop_count=2)

    with pytest.raises(ValueError, match="unknown_stage"):
        RunConfig.resolve(stage_overrides={"unknown_stage": True})


@pytest.mark.asyncio
async def test_hl_mode_13_generate_only_run_skips_every_other_stage_in_order(session):
    config = RunConfig.resolve(stage_overrides={"generate": True})
    machine = RunStateMachine(RunRepository(session), config)

    result = await machine.start(project_id="default", mode=PASSIVE)

    assert result.state == "completed"
    trace = await RunRepository(session).get_trace(result.run_id)
    assert [step.kind for step in trace.steps] == [
        "stage.generate",
        "stage.review",
        "stage.compare",
        "stage.evolve",
        "stage.validate",
        "stage.cache",
        "stage.loop_control",
    ]
    assert trace.steps[0].status == "completed"
    assert [step.status for step in trace.steps[1:]] == ["skipped"] * 6


@pytest.mark.asyncio
async def test_hl_mode_11_review_stage_receives_generate_candidates_and_emits_trace(session):
    config = RunConfig.resolve(stage_overrides={"generate": True, "review": True})
    result = await RunStateMachine(RunRepository(session), config).start(project_id="default", mode=PASSIVE)

    assert result.state == "completed"
    trace = await RunRepository(session).get_trace(result.run_id)
    review = next(step for step in trace.steps if step.kind == "stage.review")
    assert review.status == "completed"
    assert review.payload["received_candidate_count"] >= 1
    assert "reviewed_candidate_count" in review.payload


@pytest.mark.asyncio
async def test_hl_mode_14_compare_ranking_artifact_uses_one_stage_contract(session):
    config = RunConfig.resolve(
        stage_overrides={"generate": True, "compare": True},
        scoring_method="rubric",
    )

    result = await RunStateMachine(RunRepository(session), config).start(project_id="default", mode=PASSIVE)

    assert result.state == "completed"
    run = await session.get(AgentRun, result.run_id)
    artifacts = json.loads(run.artifacts)
    ranking = next(item for item in artifacts if item["kind"] == "ranking")
    assert ranking["stage"] == "compare"
    assert ranking["method"] == "rubric"
    assert [item["id"] for item in ranking["ranking"]] == ["idea-3", "idea-2", "idea-1"]
    assert {item["id"] for item in ranking["ranking"]} == {"idea-1", "idea-2", "idea-3"}

    compare = CompareStage(scoring_method="elo")
    assert compare.scoring_method == "elo"


@pytest.mark.asyncio
async def test_hl_mode_15_phase2_run_stops_at_recipe_boundary_without_reentering_generate(session):
    config = RunConfig.resolve(stage_overrides={stage.value: True for stage in StageEnum})

    result = await RunStateMachine(RunRepository(session), config).start(project_id="default", mode=PASSIVE)

    assert result.state == "completed"
    trace = await RunRepository(session).get_trace(result.run_id)
    assert [step.kind for step in trace.steps].count("stage.generate") == 1
    assert trace.steps[-1].kind == "stage.loop_control"
    assert trace.steps[-1].payload["boundary"] == "recipe-complete"


@pytest.mark.asyncio
async def test_hl_mode_20_force_quit_mid_run_preserves_completed_stage_prefix(session):
    class ForceQuitCompareStage:
        id = StageEnum.COMPARE

        async def run(self, ctx):
            raise KeyboardInterrupt("simulated force quit before compare finished")

    config = RunConfig.resolve(stage_overrides={"generate": True, "review": True, "compare": True})
    machine = RunStateMachine(
        RunRepository(session),
        config,
        stages={StageEnum.COMPARE: ForceQuitCompareStage()},
    )

    with pytest.raises(KeyboardInterrupt):
        await machine.start(project_id="default", mode=PASSIVE)

    trace = await RunRepository(session).get_trace(machine.run_id)
    assert [step.kind for step in trace.steps] == ["stage.generate", "stage.review"]
    assert all(step.status == "completed" for step in trace.steps)


@pytest.mark.asyncio
async def test_hl_mode_17_passive_evolve_edit_routes_to_review_inbox(session):
    guard = DispatchGuard(session)
    action = DispatchAction(
        mode=PASSIVE,
        action_kind="file_edit",
        target_kind="manuscript",
        target_ref="writing/manuscripts/intro.md",
        summary="Rewrite paragraph",
    )

    result = await guard.dispatch(action)

    assert result.decision.outcome == Outcome.REVIEW_INBOX.value
    assert result.applied is False
    assert result.review_item_id


@pytest.mark.asyncio
async def test_hl_mode_18_untrusted_action_routes_to_review_inbox_even_in_full_access(session):
    guard = DispatchGuard(session)
    action = DispatchAction(
        mode=FULL_ACCESS,
        action_kind="file_edit",
        target_kind="manuscript",
        target_ref="writing/manuscripts/intro.md",
        trust_origin="untrusted-external",
        justification_trust="untrusted-external",
        full_access_enabled=True,
        summary="Untrusted page suggested rewrite",
    )

    result = await guard.dispatch(action)

    assert result.decision.outcome == Outcome.REVIEW_INBOX.value
    assert result.applied is False
    assert result.review_item_id


@pytest.mark.asyncio
@pytest.mark.parametrize("action_kind", ["skill_capability_field", "permission_setting", "provider_routing"])
async def test_hl_mode_18_full_access_never_auto_edits_skill_permission_or_provider_settings(session, action_kind):
    guard = DispatchGuard(session)

    result = await guard.dispatch(
        DispatchAction(
            mode=FULL_ACCESS,
            action_kind=action_kind,
            target_kind="setting",
            target_ref=action_kind,
            full_access_enabled=True,
            summary=f"Attempt {action_kind}",
        )
    )

    assert result.decision.outcome == Outcome.APPROVAL_REQUIRED.value
    assert result.applied is False
    assert result.approval_id


@pytest.mark.asyncio
async def test_hl_consent_20_offline_only_hard_blocks_g3_send_in_every_mode(session):
    guard = DispatchGuard(session)

    result = await guard.dispatch(
        DispatchAction(
            mode=FULL_ACCESS,
            action_kind="provider_send",
            target_kind="provider",
            target_ref="openai",
            full_access_enabled=True,
            privacy=PrivacyPosture(
                g3_enabled=True,
                offline_only=True,
                egress_items=[{"type": "selection", "id_or_path": "sel-1", "label": "Selected text"}],
            ),
        )
    )

    assert result.decision.outcome == Outcome.BLOCKED.value
    assert result.applied is False
    assert result.status == "permission-denied"
    assert result.reason == "permission denied (offline)"


@pytest.mark.asyncio
async def test_hl_mode_16_run_pauses_at_budget_ceiling_and_does_not_auto_continue(session):
    config = RunConfig.resolve(stage_overrides={"generate": True})
    result = await RunStateMachine(
        RunRepository(session),
        config,
        budget=RunBudget(run_budget_tokens=1, wall_clock_seconds=120),
    ).start(project_id="default", mode=PASSIVE)

    assert result.state == "budget_blocked"
    run = await session.get(AgentRun, result.run_id)
    assert run.status == "blocked"
    trace = await RunRepository(session).get_trace(result.run_id)
    assert trace.steps[-1].kind == "budget.blocked"
    assert trace.steps[-1].payload["state"] == "budget_blocked"
    assert "continue" in trace.steps[-1].summary
