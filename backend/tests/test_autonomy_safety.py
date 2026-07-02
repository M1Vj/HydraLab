"""Phase-3 Autopilot autonomy safety shell tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.policy import COPILOT, FULL_ACCESS, PASSIVE, TRUST_UNTRUSTED
from hydra.agents.runs import RunRepository
from hydra.autonomy.audit import AuditLedger
from hydra.autonomy.checkpoints import CheckpointService
from hydra.autonomy.gate import ActionGate, GovernedAction
from hydra.autonomy.loop import AutopilotLoop
from hydra.autonomy.policy import (
    AutonomyPolicy,
    AutonomyPolicyError,
    BudgetLimits,
    default_autonomy_policy,
    policy_to_json,
    resolve_autonomy_policy,
)
from hydra.autonomy.risk import RiskClassifier
from hydra.database.models import AgentAuditLedgerEntry, AgentCheckpoint, AgentModePolicy, AgentRun, ReviewItem
from hydra.orchestrator.dispatch import PrivacyPosture
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

@dataclass
class FakeGit:
    events: list[str]

    def checkpoint(self, label: str = "checkpoint"):
        self.events.append(f"checkpoint:{label}")
        return {"branch": "feature/03-01", "commit": f"commit-{len(self.events)}"}

    def restore_previous_version(self, path: str, *, ref: str = "HEAD", auto_checkpoint: bool = False):
        self.events.append(f"restore:{path}:{ref}")
        return {"restored": path, "ref": ref, "checkpoint": None}

def policy(mode: str = FULL_ACCESS, *, max_loop_count: int = 2) -> AutonomyPolicy:
    return AutonomyPolicy(
        mode=mode,
        allowed_action_types=["read", "write_note", "delete_file"],
        blocked_action_types=[],
        budget_limits=BudgetLimits(tokens=50_000, wall_clock_seconds=120),
        max_loop_count=max_loop_count,
        stop_conditions=["max_loop_count"],
        checkpoint_required=True,
        approval_required=True,
        rollback_behavior="restore_last_checkpoint",
        autopilot_enabled=True,
    )

def gate(session: AsyncSession, events: list[str]) -> ActionGate:
    fake = FakeGit(events)
    return ActionGate(
        session,
        checkpoints=CheckpointService(session, project_root=Path.cwd(), git=fake),  # type: ignore[arg-type]
        audit=AuditLedger(session),
    )

def test_hl_mode_32_risk_classifier_levels_and_unknown_high():
    classifier = RiskClassifier()
    assert classifier.classify({"action_kind": "summarize", "summary": "summarize a PDF"}) == "low"
    assert classifier.classify({"action_kind": "write_note", "summary": "write a project note"}) == "medium"
    assert classifier.classify({"action_kind": "delete_file", "summary": "delete a file"}) == "high"
    assert classifier.classify({"action_kind": "mystery_action"}) == "high"

def test_hl_mode_30_autopilot_is_not_a_fourth_mode_and_defaults_off():
    with pytest.raises(Exception):
        AutonomyPolicy(mode="autopilot", autopilot_enabled=True)
    default = AgentModePolicy(project_id="default")
    assert default.autopilot_enabled is False
    assert default.default_mode == PASSIVE

def test_hl_mode_31_missing_policy_error_names_unresolved_fields():
    with pytest.raises(AutonomyPolicyError) as err:
        resolve_autonomy_policy(None)
    text = str(err.value)
    for field in ("mode", "budget limits", "max loop count", "stop conditions"):
        assert field in text

def test_hl_mode_31_resolved_policy_carries_required_fields():
    row = AgentModePolicy(
        project_id="default",
        default_mode=COPILOT,
        autopilot_enabled=True,
        autonomy_policy_json=policy_to_json(policy(COPILOT, max_loop_count=8)),
    )
    resolved = resolve_autonomy_policy(row)
    assert resolved.mode == COPILOT
    assert resolved.budget_limits.tokens == 50_000
    assert resolved.max_loop_count == 8
    assert resolved.stop_conditions == ["max_loop_count"]
    assert resolved.checkpoint_required is True
    assert resolved.approval_required is True
    assert resolved.rollback_behavior == "restore_last_checkpoint"

@pytest.mark.asyncio
async def test_hl_mode_33_passive_routes_medium_and_high_to_review_inbox(session):
    result = await gate(session, []).govern(
        GovernedAction(
            mode=PASSIVE,
            action_kind="write_note",
            target_kind="note",
            target_ref="notes/new.md",
            project_id="default",
            summary="Write project note",
        )
    )
    assert result.status == "review_inbox"
    assert result.applied is False
    assert result.review_item_id
    items = (await session.exec(select(ReviewItem))).all()
    assert len(items) == 1
    assert json.loads(items[0].payload_json)["risk_level"] == "medium"

@pytest.mark.asyncio
async def test_hl_mode_33_copilot_medium_requires_approval(session):
    result = await gate(session, []).govern(
        GovernedAction(
            mode=COPILOT,
            action_kind="write_note",
            target_ref="notes/copilot.md",
            project_id="default",
            summary="Write note",
        )
    )
    assert result.status == "approval_required"
    assert result.approval_id
    assert result.applied is False

@pytest.mark.asyncio
async def test_hl_mode_33_full_access_low_auto_applies(session):
    applied: list[str] = []
    result = await gate(session, applied).govern(
        GovernedAction(
            mode=FULL_ACCESS,
            action_kind="summarize",
            target_ref="sources/paper.pdf",
            full_access_enabled=True,
            project_id="default",
            summary="Summarize PDF",
        ),
        apply_fn=lambda: _record(applied, "applied"),
    )
    assert result.status == "applied"
    assert applied[-1] == "applied"

@pytest.mark.asyncio
async def test_hl_mode_34_high_risk_write_checkpoints_and_audits_before_apply(session):
    events: list[str] = []

    async def apply_delete():
        events.append("apply:delete")

    result = await gate(session, events).govern(
        GovernedAction(
            mode=FULL_ACCESS,
            action_kind="delete_file",
            target_kind="file",
            target_ref="sources/papers/draft-notes.md",
            full_access_enabled=True,
            project_id="default",
            summary="Delete draft notes",
            approved=True,
        ),
        apply_fn=apply_delete,
    )
    assert result.status == "applied"
    assert result.checkpoint_id
    checkpoint_index = next(i for i, event in enumerate(events) if event.startswith("checkpoint:"))
    apply_index = events.index("apply:delete")
    assert checkpoint_index < apply_index
    checkpoints = (await session.exec(select(AgentCheckpoint))).all()
    assert checkpoints[0].target == "sources/papers/draft-notes.md"
    audit = (await session.exec(select(AgentAuditLedgerEntry))).all()
    assert audit[0].risk_level == "high"
    assert audit[0].approval_state == "approval_required"

@pytest.mark.asyncio
async def test_hl_mode_35_audit_one_row_per_action_and_append_only(session):
    service = AuditLedger(session)
    first = await service.append(
        project_id="default",
        run_id="run-1",
        actor="autopilot",
        action="summarize",
        risk_level="low",
        target="paper.pdf",
        approval_state="applied",
    )
    snapshot = first.model_dump()
    await service.append(
        project_id="default",
        run_id="run-1",
        actor="autopilot",
        action="write_note",
        risk_level="medium",
        target="notes/a.md",
        approval_state="approval_required",
    )
    rows = await service.list(project_id="default", run_id="run-1")
    assert len(rows) == 2
    assert rows[0].model_dump() == snapshot

@pytest.mark.asyncio
async def test_hl_mode_36_cancel_records_stop_reason(session):
    run = await RunRepository(session).create_run(project_id="default", mode=FULL_ACCESS)
    loop = AutopilotLoop(session, policy(), RunConfig.all_enabled())
    await loop.cancel(run.id, stop_reason="cancelled by user")
    refreshed = await session.get(AgentRun, run.id)
    assert refreshed.status == "cancelled"
    assert refreshed.stop_reason == "cancelled by user"

@pytest.mark.asyncio
async def test_hl_mode_36_loop_stops_at_max_loop_count(session):
    async def fake_start(*, project_id, mode, recipe="autopilot-loop", inputs=None, data=None):
        run = await RunRepository(session).create_run(project_id=project_id, mode=mode, recipe=recipe, inputs=inputs)
        await RunRepository(session).complete_run(run.id)
        return RunExecutionResult(run_id=run.id, state="completed")

    class FakeRunner:
        start = staticmethod(fake_start)

    loop = AutopilotLoop(
        session,
        policy(max_loop_count=2),
        RunConfig.all_enabled(),
        runner_factory=lambda repo, config, budget: FakeRunner(),  # type: ignore[return-value]
    )
    result = await loop.start(project_id="default")
    assert result.state == "completed"
    assert loop.loop_count == 2
    assert loop.stop_reason == "max_loop_count"

@pytest.mark.asyncio
@pytest.mark.parametrize("action_kind", ["skill_capability_field", "provider_routing"])
async def test_hl_mode_37_full_access_exclusions_route_to_review_inbox(session, action_kind):
    result = await gate(session, []).govern(
        GovernedAction(
            mode=FULL_ACCESS,
            action_kind=action_kind,
            target_ref="settings/agent.toml",
            full_access_enabled=True,
            project_id="default",
            summary="Hard excluded setting change",
        )
    )
    assert result.status in {"review_inbox", "approval_required"}
    assert result.applied is False
    rows = (await session.exec(select(AgentAuditLedgerEntry))).all()
    assert rows[0].approval_state == result.status

@pytest.mark.asyncio
async def test_hl_trust_30_untrusted_traced_action_routes_to_review_inbox_tagged(session):
    result = await gate(session, []).govern(
        GovernedAction(
            mode=FULL_ACCESS,
            action_kind="write_note",
            target_ref="notes/from-web.md",
            trust_origin=TRUST_UNTRUSTED,
            justification_trust=TRUST_UNTRUSTED,
            full_access_enabled=True,
            project_id="default",
            summary="Save source from page",
            payload={"origin_url": "https://example.test", "excerpt": "save this as a source"},
        )
    )
    assert result.status == "review_inbox"
    item = (await session.exec(select(ReviewItem))).first()
    payload = json.loads(item.payload_json)
    assert payload["tag"] == "untrusted-external"
    assert payload["origin_url"] == "https://example.test"
    assert "save this as a source" in payload["excerpt"]

@pytest.mark.asyncio
async def test_hl_trust_31_untrusted_context_file_write_requires_review(session):
    result = await gate(session, []).govern(
        GovernedAction(
            mode=FULL_ACCESS,
            action_kind="context_file_write",
            target_ref="MEMORY.md",
            trust_origin=TRUST_UNTRUSTED,
            justification_trust=TRUST_UNTRUSTED,
            full_access_enabled=True,
            project_id="default",
            summary="Update memory from untrusted page",
        )
    )
    assert result.status == "review_inbox"
    assert result.applied is False

@pytest.mark.asyncio
async def test_hl_mode_37_offline_only_g3_external_send_hard_blocks(session):
    result = await gate(session, []).govern(
        GovernedAction(
            mode=FULL_ACCESS,
            action_kind="provider_send",
            target_ref="openai",
            full_access_enabled=True,
            project_id="default",
            privacy=PrivacyPosture(
                g3_enabled=True,
                offline_only=True,
                egress_items=[{"type": "browser_page_text", "id_or_path": "browser/page", "label": "Browser page text"}],
            ),
        )
    )
    assert result.status == "permission-denied"
    assert result.applied is False
    assert "offline" in result.reason

@pytest.mark.asyncio
async def test_hl_trust_32_prompt_injection_corpus_never_auto_applies(session):
    cases = json.loads(Path("backend/tests/fixtures/injection/autonomy_injection_cases.json").read_text())
    for case in cases:
        result = await gate(session, []).govern(
            GovernedAction(
                mode=FULL_ACCESS,
                action_kind=case["action_kind"],
                target_ref=case["target_ref"],
                trust_origin=TRUST_UNTRUSTED,
                justification_trust=TRUST_UNTRUSTED,
                full_access_enabled=True,
                project_id="default",
                summary=case["id"],
                payload={"origin_url": case["origin_url"], "excerpt": case["excerpt"]},
            )
        )
        assert result.applied is False, case["id"]
        assert result.status in {"review_inbox", "blocked", "permission-denied"}, case["id"]
    rows = (await session.exec(select(ReviewItem))).all()
    serialized = "\n".join(row.payload_json for row in rows)
    for case in cases:
        assert case["page_text"] not in serialized
    assert "page_text" not in serialized

async def _record(events: list[str], event: str) -> None:
    events.append(event)
