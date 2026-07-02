"""Phase-2 agent runtime, Agent Access Mode, and skill-governance tests.

Covers every @HL-* acceptance scenario in
`.agents/features/02-assistant-co-scientist/01-agent-runtime-skills.md` that is
backend-testable, plus the branch's locked-decision guardrails (DEC-5/6/11).
"""

import json

import pytest
import pytest_asyncio
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

from hydra.agents.approvals import ApprovalService
from hydra.agents.capabilities import CapabilityDenied, check_capability, require_capability
from hydra.agents.contracts import Approval, Artifact, Run, RunStatus, Skill, Trace
from hydra.agents.policy import (
    FULL_ACCESS,
    COPILOT,
    PASSIVE,
    VALID_MODES,
    InvalidModeError,
    Outcome,
    WriteRequest,
    evaluate_write,
    normalize_mode,
)
from hydra.agents.runs import RunBudget, RunRepository, budget_exceeded
from hydra.database.models import AgentModePolicy
from hydra.settings.toml_config import SettingsValidationError, default_settings, validate_settings
from hydra.skills.registry import (
    builtin_skills_dir,
    edit_skill_text,
    factory_text,
    load_skill_registry,
    parse_skill_file,
    restore_skill,
    set_skill_enabled,
)


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


VALID_SKILL = """---
id: {id}
name: {name}
version: "1.0.0"
scope: {scope}
description: A valid skill.
enabled_by_default: {enabled}
allowed_capabilities:
  - read_context
risk_level: low
requires_approval: false
tags:
  - test
---

# Purpose
p
# When To Use
w
# Inputs
i
# Workflow
wf
# Outputs
o
# Safety
s
# References
r
"""

MISSING_RISK = """---
id: citation-check
name: Citation Check
version: "1.0.0"
scope: project
description: Missing risk_level.
enabled_by_default: false
allowed_capabilities: []
requires_approval: true
tags: []
---

# Purpose
p
# When To Use
w
# Inputs
i
# Workflow
wf
# Outputs
o
# Safety
s
# References
r
"""


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- MODE-01
def test_hl_mode_01_normalize_rejects_values_outside_canonical_set():
    for value in VALID_MODES:
        assert normalize_mode(value) == value
    for bad in ("autopilot", "yolo", "suggest-only", "", None, "FULL"):
        with pytest.raises(InvalidModeError):
            normalize_mode(bad)


def test_hl_mode_01_settings_reject_out_of_set_default_mode():
    data = default_settings()
    data["assistant"]["default_mode"] = "autopilot"
    with pytest.raises(SettingsValidationError):
        validate_settings(data)
    # A canonical value round-trips fine.
    data["assistant"]["default_mode"] = "copilot"
    validate_settings(data)


# --------------------------------------------------------------------------- MODE-02
@pytest.mark.asyncio
async def test_hl_mode_02_rejecting_copilot_edit_leaves_workspace_unchanged(session):
    service = ApprovalService(session)
    workspace = {"writing/manuscripts/intro.md": "original"}
    approval = await service.request(
        action_kind="file_edit",
        mode=COPILOT,
        project_id="default",
        target_kind="manuscript",
        target_ref="writing/manuscripts/intro.md",
        summary="insert citation",
    )

    async def apply_fn():
        workspace["writing/manuscripts/intro.md"] = "edited"

    result = await service.resolve(approval.id, decision="rejected", apply_fn=apply_fn)
    assert result.applied is False
    assert result.status == "rejected"
    # No file, row, sidecar or context file changed.
    assert workspace["writing/manuscripts/intro.md"] == "original"
    refreshed = await service.get(approval.id)
    assert refreshed.status == "rejected"


@pytest.mark.asyncio
async def test_hl_mode_02_approving_copilot_edit_applies_once(session):
    service = ApprovalService(session)
    applied = {"count": 0}
    approval = await service.request(action_kind="file_edit", mode=COPILOT, project_id="default")

    async def apply_fn():
        applied["count"] += 1

    result = await service.resolve(approval.id, decision="approved", apply_fn=apply_fn)
    assert result.applied is True
    assert applied["count"] == 1


# --------------------------------------------------------------------------- MODE-03
def test_hl_mode_03_full_access_low_risk_applies_with_checkpoint():
    decision = evaluate_write(
        WriteRequest(
            mode=FULL_ACCESS,
            action_kind="tag_normalize",
            target_kind="source",
            target_ref="Attention Is All You Need",
            risk_level="low",
            full_access_enabled=True,
        )
    )
    assert decision.outcome == Outcome.APPLY.value
    assert decision.applied is True
    assert decision.checkpoint_required is True
    assert decision.logged is True


def test_hl_mode_03_full_access_not_enabled_falls_back_to_approval():
    decision = evaluate_write(
        WriteRequest(mode=FULL_ACCESS, action_kind="tag_normalize", risk_level="low", full_access_enabled=False)
    )
    assert decision.outcome == Outcome.APPROVAL_REQUIRED.value


@pytest.mark.asyncio
async def test_hl_mode_03_full_access_defaults_off_on_new_project(session):
    # A fresh project has never enabled Full Access.
    policy = await session.get(AgentModePolicy, "brand-new")
    assert policy is None
    default = AgentModePolicy(project_id="brand-new")
    assert default.default_mode == "passive"
    assert default.full_access_enabled is False


# --------------------------------------------------------------------------- MODE-04
@pytest.mark.parametrize("mode", list(VALID_MODES))
def test_hl_mode_04_untrusted_write_routes_to_review_inbox_in_every_mode(mode):
    decision = evaluate_write(
        WriteRequest(
            mode=mode,
            action_kind="context_file_write",
            target_kind="context_file",
            target_ref="MEMORY.md",
            trust_origin="untrusted-external",
            justification_trust="untrusted-external",
            full_access_enabled=True,
        )
    )
    assert decision.outcome == Outcome.REVIEW_INBOX.value
    assert decision.review_inbox is True
    assert "untrusted" in decision.reason


def test_hl_mode_04_no_arbitrary_code_execution_in_any_mode():
    for mode in VALID_MODES:
        decision = evaluate_write(
            WriteRequest(mode=mode, action_kind="shell", high_risk_category="shell", full_access_enabled=True)
        )
        assert decision.outcome == Outcome.BLOCKED.value


def test_hl_mode_04_high_risk_category_never_auto_applies():
    decision = evaluate_write(
        WriteRequest(mode=FULL_ACCESS, action_kind="file_edit", high_risk_category="secrets", full_access_enabled=True)
    )
    assert decision.outcome == Outcome.REVIEW_INBOX.value


# --------------------------------------------------------------------------- MODE-05
def test_hl_mode_05_full_access_never_auto_edits_skill_risk_fields():
    decision = evaluate_write(
        WriteRequest(
            mode=FULL_ACCESS,
            action_kind="skill_capability_field",
            target_kind="skill",
            target_ref="citation-check",
            risk_level="low",
            full_access_enabled=True,
        )
    )
    assert decision.outcome == Outcome.REVIEW_INBOX.value
    assert decision.review_inbox is True
    assert decision.reason == "skill capability field is a hard exclusion"


@pytest.mark.parametrize(
    "action_kind",
    ["skill_capability_field", "permission_setting", "privacy_setting", "consent_setting", "provider_routing"],
)
def test_hl_mode_05_full_access_exclusions_all_downgrade(action_kind):
    decision = evaluate_write(
        WriteRequest(mode=FULL_ACCESS, action_kind=action_kind, risk_level="low", full_access_enabled=True)
    )
    assert decision.outcome == Outcome.REVIEW_INBOX.value
    assert decision.logged is True


# --------------------------------------------------------------------------- ASSIST-01
def test_hl_assist_01_run_result_uses_only_hydralab_vocabulary():
    run = Run(
        id="run-1",
        project_id="default",
        mode=PASSIVE,
        status=RunStatus.COMPLETED.value,
        trace=Trace(run_id="run-1"),
        artifacts=[Artifact(id="a1", kind="summary", ref="brief.md", summary="short brief")],
        approvals=[Approval(id="ap1", action_kind="write_annotation")],
    )
    result = run.public_result()
    assert result["vocabulary"] == ["Run", "Tool", "Skill", "Trace", "Artifact", "Approval"]
    assert set(result) >= {"trace", "artifacts", "approvals", "run"}
    serialized = json.dumps(result).lower()
    for framework in ("openai", "langgraph", "pydantic_ai", "pydanticai", "crewai"):
        assert framework not in serialized


# --------------------------------------------------------------------------- ASSIST-02
def test_hl_assist_02_disabled_skill_stays_disabled_after_reopen(tmp_path):
    project_dir = tmp_path / "project"
    state_dir = tmp_path / "state"
    _write(project_dir / "citation-check.md", VALID_SKILL.format(id="citation-check", name="Citation Check", scope="project", enabled="true"))

    registry = load_skill_registry(project_dir=project_dir, state_dir=state_dir)
    citation = registry.get("citation-check")
    summarize = registry.get("summarize-source")  # built-in, enabled by default
    assert citation.enabled is True
    assert summarize.enabled is True

    set_skill_enabled(state_dir, citation, False)

    # Reopen the project (fresh registry load with the same state dir).
    reopened = load_skill_registry(project_dir=project_dir, state_dir=state_dir)
    assert reopened.get("citation-check").enabled is False
    assert reopened.get("summarize-source").enabled is True


# --------------------------------------------------------------------------- ASSIST-03
def test_hl_assist_03_skill_missing_required_key_cannot_enable(tmp_path):
    project_dir = tmp_path / "project"
    state_dir = tmp_path / "state"
    _write(project_dir / "citation-check.md", MISSING_RISK)
    registry = load_skill_registry(builtin_dir=tmp_path / "none", project_dir=project_dir, state_dir=state_dir)
    skill = registry.get("citation-check")
    assert skill.enabled is False
    assert "risk_level" in skill.disabled_reason
    with pytest.raises(ValueError):
        set_skill_enabled(state_dir, skill, True)


# --------------------------------------------------------------------------- ASSIST-04
@pytest.mark.asyncio
async def test_hl_assist_04_trace_persists_incrementally_and_cancel_keeps_prefix(session):
    runs = RunRepository(session)
    run = await runs.create_run(project_id="default", mode=FULL_ACCESS)
    await runs.append_step(run.id, kind="plan", summary="planned", tokens=100)
    await runs.append_step(run.id, kind="checkpoint", summary="before write", tokens=0)
    await runs.append_step(run.id, kind="write", summary="normalized tag", tokens=50)

    cancelled = await runs.cancel_run(run.id)
    assert cancelled.status == RunStatus.CANCELLED.value

    # A late step is not appended after cancel in this scenario; the completed
    # prefix survives intact.
    trace = await runs.get_trace(run.id)
    assert [step.kind for step in trace.steps] == ["plan", "checkpoint", "write"]
    assert trace.tokens == 150
    assert cancelled.tokens_used == 150


def test_hl_assist_04_budget_ceiling_blocks():
    budget = RunBudget(run_budget_tokens=60_000, wall_clock_seconds=120)
    assert budget_exceeded(tokens_used=60_000, elapsed_seconds=1, budget=budget) is True
    assert budget_exceeded(tokens_used=1, elapsed_seconds=120, budget=budget) is True
    assert budget_exceeded(tokens_used=1, elapsed_seconds=1, budget=budget) is False


# --------------------------------------------------------------------------- ASSIST-05
def test_hl_assist_05_restore_builtin_returns_factory_text(tmp_path):
    state_dir = tmp_path / "state"
    factory = factory_text("summarize-source")
    assert factory is not None
    _, factory_body = parse_skill_file(factory)

    edit_skill_text(state_dir, "summarize-source", factory.replace("grounded summary", "COMPLETELY REWRITTEN"))
    edited = load_skill_registry(state_dir=state_dir).get("summarize-source")
    assert "COMPLETELY REWRITTEN" in edited.body
    assert edited.edited is True

    restore_skill(state_dir, "summarize-source")
    restored = load_skill_registry(state_dir=state_dir).get("summarize-source")
    assert restored.body == factory_body
    assert "COMPLETELY REWRITTEN" not in restored.body


def test_hl_assist_05_enabled_state_survives_body_restore(tmp_path):
    state_dir = tmp_path / "state"
    registry = load_skill_registry(state_dir=state_dir)
    draft = registry.get("draft-outline")  # ships disabled by default
    set_skill_enabled(state_dir, draft, True)
    edit_skill_text(state_dir, "draft-outline", factory_text("draft-outline"))
    restore_skill(state_dir, "draft-outline")
    assert load_skill_registry(state_dir=state_dir).get("draft-outline").enabled is True


# --------------------------------------------------------------------------- ASSIST-06
@pytest.mark.asyncio
async def test_hl_assist_06_capability_outside_allowances_is_refused_and_traced(session):
    skill = Skill(
        id="summarize-source",
        name="Summarize Source",
        scope="builtin",
        allowed_capabilities=["read-source", "write-annotation"],
    )
    check = check_capability(skill, "send-email")
    assert check.allowed is False
    with pytest.raises(CapabilityDenied):
        require_capability(skill, "send-email")

    runs = RunRepository(session)
    run = await runs.create_run(project_id="default", mode=PASSIVE)
    step = await runs.append_step(
        run.id,
        kind="capability_denied",
        status="denied",
        skill_id=skill.id,
        denied_capability="send-email",
        summary="email capability refused",
    )
    assert step.skill_id == "summarize-source"
    assert step.denied_capability == "send-email"
    trace = await runs.get_trace(run.id)
    assert trace.steps[0].denied_capability == "send-email"
    assert trace.steps[0].skill_id == "summarize-source"


def test_builtin_skills_dir_exists():
    assert builtin_skills_dir().exists()
