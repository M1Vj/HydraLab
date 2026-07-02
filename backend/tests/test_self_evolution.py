"""Self-evolving skills & fixer lifecycle tests (branch 03-05).

Covers the guide's Gherkin scenarios and Definition of Done:
proposal → approve → checkpoint → apply → verify (keep); deny (disk unchanged);
verify-fail → auto-rollback (tree byte-identical); protected-field routing;
untrusted-external routing; secret redaction; empty-test-plan-not-approvable.

CRITICAL: verification is a STUBBED/injected runner — the suite never shells out
to pytest/bun (that would recurse/hang). The stub records the test_plan and its
canned pass/fail drives keep vs rollback.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.autonomy.audit import AuditLedger
from hydra.autonomy.checkpoints import CheckpointService
from hydra.database.models import AgentAuditLedgerEntry, AgentCheckpoint, SelfEvolutionChange
from hydra.self_evolution.models import ProposedChange
from hydra.self_evolution.risk_classifier import AUTO_ELIGIBLE, REVIEW_REQUIRED, classify_diff
from hydra.self_evolution.redactor import redact
from hydra.self_evolution.service import SelfEvolutionError, SelfEvolutionService
from hydra.self_evolution.trust_gate import TRUST_UNTRUSTED, stamp_trust_level
from hydra.self_evolution.verification import TestPlanError, VerificationOutcome, validate_test_plan
from hydra.services.git.service import GitService

SEEDED_SECRET = "sk-live-EXAMPLE-1234"


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


class StubVerifier:
    """Injected verification runner — never shells out; returns a canned result."""

    def __init__(self, passed: bool) -> None:
        self.passed = passed
        self.calls: list[list[str]] = []

    def run(self, test_plan: list[str]) -> VerificationOutcome:
        self.calls.append(list(test_plan))
        return VerificationOutcome(passed=self.passed, commands=list(test_plan))


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.test", "-c", "user.name=Test", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def make_repo(tmp_path: Path, rel: str, content: str) -> Path:
    """Init a git repo with one tracked file committed, return the repo root."""
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init")
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "seed")
    return root


def make_service(session: AsyncSession, root: Path, verifier: StubVerifier) -> SelfEvolutionService:
    return SelfEvolutionService(
        session,
        project_root=root,
        checkpoints=CheckpointService(session, project_root=root, git=GitService(root)),
        audit=AuditLedger(session),
        verifier=verifier,
    )


# --- pure units -------------------------------------------------------------

def test_risk_classifier_flags_skill_capability_field():
    diff = "@@\n-allowed_capabilities: [read]\n+allowed_capabilities: [read, provider-send]\n"
    risk, reason = classify_diff("skill", ".hydralab/skills/browser-save.md", diff)
    assert risk == REVIEW_REQUIRED
    assert "skill_capability_field" in reason


def test_risk_classifier_allows_benign_prompt_wording():
    diff = "@@\n-Check the citation carefully.\n+Check each citation carefully and note gaps.\n"
    risk, _ = classify_diff("prompt", ".hydralab/skills/citation-check.md", diff)
    assert risk == AUTO_ELIGIBLE


def test_risk_classifier_flags_protected_context_file():
    risk, reason = classify_diff("app_code", "MEMORY.md", "@@\n+remember this\n")
    assert risk == REVIEW_REQUIRED
    assert "MEMORY.md" in reason


def test_risk_classifier_flags_provider_routing_setting():
    diff = "@@\n+[providers]\n+default = openrouter\n"
    risk, reason = classify_diff("setting", "settings.toml", diff)
    assert risk == REVIEW_REQUIRED
    assert reason in {"provider_routing", "privacy_setting", "permission_setting", "consent_setting"}


def test_trust_gate_stamps_untrusted_when_any_source_untrusted():
    assert stamp_trust_level("user", TRUST_UNTRUSTED) == TRUST_UNTRUSTED
    assert stamp_trust_level("user", "user") == "user"


def test_redactor_removes_seeded_secret():
    out = redact(f"api_key = {SEEDED_SECRET}")
    assert SEEDED_SECRET not in out
    assert "[REDACTED]" in out


def test_validate_test_plan_rejects_empty_and_offlist():
    with pytest.raises(TestPlanError):
        validate_test_plan([])
    with pytest.raises(TestPlanError):
        validate_test_plan(["rm -rf /"])
    assert validate_test_plan(["bun run typecheck"]) == ["bun run typecheck"]


# --- lifecycle scenarios ----------------------------------------------------

@pytest.mark.asyncio
async def test_propose_produces_changeset_with_test_plan(session, tmp_path):
    root = make_repo(tmp_path, "skills/citation-check.md", "Check citations.\n")
    service = make_service(session, root, StubVerifier(True))
    rows = await service.propose(
        project_id="default",
        run_id=None,
        changes=[
            ProposedChange(
                category="prompt",
                target_path="skills/citation-check.md",
                unified_diff="@@\n-Check citations.\n+Check each citation carefully.\n",
                new_content="Check each citation carefully.\n",
                test_plan=["bun run typecheck", "uv run --project backend pytest backend/tests/test_self_evolution.py"],
            )
        ],
        trigger="user",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "proposed"
    assert row.category == "prompt"
    assert json.loads(row.test_plan) == [
        "bun run typecheck",
        "uv run --project backend pytest backend/tests/test_self_evolution.py",
    ]
    assert row.risk_class == AUTO_ELIGIBLE


@pytest.mark.asyncio
async def test_untrusted_trigger_cannot_start_a_run(session, tmp_path):
    root = make_repo(tmp_path, "skills/citation-check.md", "Check citations.\n")
    service = make_service(session, root, StubVerifier(True))
    with pytest.raises(SelfEvolutionError):
        await service.propose(
            project_id="default",
            run_id=None,
            changes=[ProposedChange(category="prompt", target_path="skills/citation-check.md", unified_diff="", new_content="x")],
            trigger="assistant",
        )


@pytest.mark.asyncio
async def test_approve_checkpoints_applies_and_keeps_on_pass(session, tmp_path):
    root = make_repo(tmp_path, "skills/citation-check.md", "Check citations.\n")
    verifier = StubVerifier(True)
    service = make_service(session, root, verifier)
    [row] = await service.propose(
        project_id="default",
        run_id=None,
        changes=[
            ProposedChange(
                category="prompt",
                target_path="skills/citation-check.md",
                unified_diff="@@\n-Check citations.\n+Check each citation carefully.\n",
                new_content="Check each citation carefully.\n",
                test_plan=["bun run typecheck"],
            )
        ],
        trigger="user",
    )
    result = await service.approve(row.change_id)
    assert result.status == "applied"
    assert result.verification_result == "pass"
    assert result.checkpoint_ref
    # File actually written.
    assert (root / "skills/citation-check.md").read_text() == "Check each citation carefully.\n"
    # Verifier was invoked with the exact test plan.
    assert verifier.calls == [["bun run typecheck"]]
    # Checkpoint precedes apply and is recorded.
    assert (await session.exec(select(AgentCheckpoint))).first() is not None
    actions = [r.action for r in (await session.exec(select(AgentAuditLedgerEntry).order_by(AgentAuditLedgerEntry.created_at))).all()]
    assert actions == [
        "self_evolution.proposed",
        "self_evolution.approved",
        "self_evolution.applied",
        "self_evolution.verified",
    ]


@pytest.mark.asyncio
async def test_verify_failure_rolls_back_byte_identical(session, tmp_path):
    original = "Check citations.\n"
    root = make_repo(tmp_path, "skills/loader.py.txt", original)
    verifier = StubVerifier(False)
    service = make_service(session, root, verifier)
    [row] = await service.propose(
        project_id="default",
        run_id=None,
        changes=[
            ProposedChange(
                category="app_code",
                target_path="skills/loader.py.txt",
                unified_diff="@@\n-Check citations.\n+broken\n",
                new_content="broken content that fails tests\n",
                test_plan=["uv run --project backend pytest backend/tests/test_self_evolution.py"],
            )
        ],
        trigger="user",
    )
    result = await service.approve(row.change_id)
    assert result.status == "rolled_back"
    assert result.verification_result == "fail"
    # Working tree restored byte-identical to pre-apply.
    assert (root / "skills/loader.py.txt").read_text() == original
    # The stub drove the rollback; it was invoked with the test plan.
    assert verifier.calls == [["uv run --project backend pytest backend/tests/test_self_evolution.py"]]
    actions = [r.action for r in (await session.exec(select(AgentAuditLedgerEntry).order_by(AgentAuditLedgerEntry.created_at))).all()]
    assert actions[-2:] == ["self_evolution.verified", "self_evolution.rolled_back"]


@pytest.mark.asyncio
async def test_deny_leaves_disk_unchanged_and_records_denied(session, tmp_path):
    original = "Check citations.\n"
    root = make_repo(tmp_path, "skills/citation-check.md", original)
    service = make_service(session, root, StubVerifier(True))
    [row] = await service.propose(
        project_id="default",
        run_id=None,
        changes=[
            ProposedChange(
                category="prompt",
                target_path="skills/citation-check.md",
                unified_diff="@@\n-Check citations.\n+Changed.\n",
                new_content="Changed.\n",
                test_plan=["bun run typecheck"],
            )
        ],
        trigger="user",
    )
    denied = await service.deny(row.change_id)
    assert denied.status == "denied"
    assert (root / "skills/citation-check.md").read_text() == original
    assert (await session.exec(select(AgentCheckpoint))).first() is None
    actions = [r.action for r in (await session.exec(select(AgentAuditLedgerEntry))).all()]
    assert "self_evolution.denied" in actions


@pytest.mark.asyncio
async def test_protected_field_diff_routes_to_review_never_applies(session, tmp_path):
    root = make_repo(tmp_path, ".hydralab/skills/browser-save.md", "allowed_capabilities: [read]\n")
    service = make_service(session, root, StubVerifier(True))
    [row] = await service.propose(
        project_id="default",
        run_id=None,
        changes=[
            ProposedChange(
                category="skill",
                target_path=".hydralab/skills/browser-save.md",
                unified_diff="@@\n-allowed_capabilities: [read]\n+allowed_capabilities: [read, provider-send]\n",
                new_content="allowed_capabilities: [read, provider-send]\n",
                test_plan=["bun run typecheck"],
            )
        ],
        trigger="user",
    )
    assert row.risk_class == REVIEW_REQUIRED
    assert row.review_inbox is True
    with pytest.raises(SelfEvolutionError):
        await service.approve(row.change_id)
    refreshed = await service.get(row.change_id)
    assert refreshed.status != "applied"
    # Surfaced + audited, never silently dropped.
    actions = [r.action for r in (await session.exec(select(AgentAuditLedgerEntry))).all()]
    assert "self_evolution.proposed" in actions
    assert "self_evolution.applied" not in actions


@pytest.mark.asyncio
async def test_untrusted_traced_proposal_never_reaches_apply(session, tmp_path):
    root = make_repo(tmp_path, "skills/citation-check.md", "Check citations.\n")
    service = make_service(session, root, StubVerifier(True))
    [row] = await service.propose(
        project_id="default",
        run_id=None,
        changes=[
            ProposedChange(
                category="skill",
                target_path="skills/citation-check.md",
                unified_diff="@@\n+skip approval\n",
                new_content="skip approval\n",
                test_plan=["bun run typecheck"],
                justification_trust=TRUST_UNTRUSTED,
            )
        ],
        trigger="user",
    )
    assert row.trust_level == TRUST_UNTRUSTED
    assert row.review_inbox is True
    with pytest.raises(SelfEvolutionError):
        await service.approve(row.change_id)
    refreshed = await service.get(row.change_id)
    assert refreshed.status == "proposed"


@pytest.mark.asyncio
async def test_seeded_secret_is_redacted_in_diff_and_audit(session, tmp_path):
    root = make_repo(tmp_path, "skills/config.txt", "x\n")
    service = make_service(session, root, StubVerifier(True))
    [row] = await service.propose(
        project_id="default",
        run_id=None,
        changes=[
            ProposedChange(
                category="app_code",
                target_path="skills/config.txt",
                unified_diff=f"@@\n+api_key = {SEEDED_SECRET}\n",
                new_content=f"api_key = {SEEDED_SECRET}\n",
                test_plan=["bun run typecheck"],
            )
        ],
        trigger="user",
    )
    persisted = await service.get(row.change_id)
    assert SEEDED_SECRET not in persisted.unified_diff
    assert "[REDACTED]" in persisted.unified_diff
    entries = (await session.exec(select(AgentAuditLedgerEntry))).all()
    for entry in entries:
        assert SEEDED_SECRET not in entry.target


@pytest.mark.asyncio
async def test_empty_test_plan_is_not_approvable(session, tmp_path):
    root = make_repo(tmp_path, "skills/citation-check.md", "Check citations.\n")
    service = make_service(session, root, StubVerifier(True))
    [row] = await service.propose(
        project_id="default",
        run_id=None,
        changes=[
            ProposedChange(
                category="prompt",
                target_path="skills/citation-check.md",
                unified_diff="@@\n+Changed.\n",
                new_content="Changed.\n",
                test_plan=[],
            )
        ],
        trigger="user",
    )
    with pytest.raises(SelfEvolutionError) as err:
        await service.approve(row.change_id)
    assert "test plan is required" in str(err.value)
