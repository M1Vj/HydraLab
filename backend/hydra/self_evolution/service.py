"""Self-evolution proposal lifecycle service (branch 03-05).

The never-silent gate: ``propose → explicit per-change approval → checkpoint →
apply → auto-verify → keep-or-auto-rollback``, plus ``deny``. Every transition is
appended to the reused 03-01 append-only audit ledger; every apply is preceded by
a 03-01 checkpoint; verification runs only through the fixed allowlist runner.

Hard invariants enforced here:
- No proposal auto-applies. Apply happens only on an explicit ``approve`` call.
- A checkpoint MUST precede any disk write; if the checkpoint cannot be created,
  apply aborts with no write and the change stays ``approved`` (audited, never
  silently dropped).
- Post-apply verification failure restores the pre-apply checkpoint and marks the
  change ``rolled_back`` with the working tree byte-identical to pre-apply.
- ``untrusted-external`` proposals and ``review_required`` (protected-field)
  proposals never reach the apply path — they route to the Review Inbox.
- Secrets are redacted from the persisted diff and from every audit payload.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.autonomy.audit import AuditLedger
from hydra.autonomy.checkpoints import CheckpointError, CheckpointService
from hydra.database.models import SelfEvolutionChange, uuid_text
from hydra.self_evolution.models import ProposedChange
from hydra.self_evolution.redactor import redact as _redact
from hydra.self_evolution.risk_classifier import REVIEW_REQUIRED, classify_diff
from hydra.self_evolution.trust_gate import (
    TRUST_UNTRUSTED,
    is_untrusted,
    stamp_trust_level,
)
from hydra.self_evolution.verification import (
    TestPlanError,
    VerificationOutcome,
    VerificationRunner,
    validate_test_plan,
)

# Audit action names (append-only ledger, HL-ASSIST-35).
ACTION_PROPOSED = "self_evolution.proposed"
ACTION_APPROVED = "self_evolution.approved"
ACTION_APPLIED = "self_evolution.applied"
ACTION_VERIFIED = "self_evolution.verified"
ACTION_ROLLED_BACK = "self_evolution.rolled_back"
ACTION_DENIED = "self_evolution.denied"
ACTION_CHECKPOINT_FAILED = "self_evolution.checkpoint_failed"

STATUS_PROPOSED = "proposed"
STATUS_APPROVED = "approved"
STATUS_APPLIED = "applied"
STATUS_ROLLED_BACK = "rolled_back"
STATUS_DENIED = "denied"


class SelfEvolutionError(RuntimeError):
    """Raised when a lifecycle guard refuses a transition (with a clear reason)."""


def public_change(row: SelfEvolutionChange) -> dict[str, object]:
    """Serialize a change row for the API/UI (already redacted at persistence)."""
    return {
        "id": row.id,
        "change_id": row.change_id,
        "changeset_id": row.changeset_id,
        "project_id": row.project_id,
        "run_id": row.run_id,
        "category": row.category,
        "target_path": row.target_path,
        "unified_diff": row.unified_diff,
        "test_plan": json.loads(row.test_plan or "[]"),
        "risk_class": row.risk_class,
        "risk_reason": row.risk_reason,
        "trust_level": row.trust_level,
        "origin": row.origin,
        "status": row.status,
        "checkpoint_ref": row.checkpoint_ref,
        "verification_result": row.verification_result,
        "review_inbox": bool(row.review_inbox),
        "created_at": row.created_at.timestamp(),
        "updated_at": row.updated_at.timestamp(),
    }


class SelfEvolutionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        project_root: Path,
        checkpoints: CheckpointService,
        audit: AuditLedger,
        verifier: VerificationRunner,
        redactor: Callable[[str], str] = _redact,
    ) -> None:
        self.session = session
        self.project_root = Path(project_root).resolve()
        self.checkpoints = checkpoints
        self.audit = audit
        self.verifier = verifier
        self.redact = redactor

    # -- audit helper --------------------------------------------------------
    async def _audit(
        self, row: SelfEvolutionChange, *, action: str, approval_state: str, actor: str
    ) -> None:
        # Encode change id / category / checkpoint ref into the ledger target;
        # the shared ledger schema has no dedicated columns for those. Redact so
        # no secret can leak into the forensic trail.
        target = self.redact(f"{row.change_id}:{row.category}:{row.checkpoint_ref or '-'}:{row.target_path}")
        await self.audit.append(
            project_id=row.project_id,
            run_id=row.run_id,
            actor=actor,
            action=action,
            risk_level="high" if row.risk_class == REVIEW_REQUIRED else "medium",
            target=target,
            approval_state=approval_state,
        )

    # -- propose -------------------------------------------------------------
    async def propose(
        self,
        *,
        project_id: str,
        run_id: str | None,
        changes: Iterable[ProposedChange],
        trigger: str = "user",
        actor: str = "assistant",
    ) -> list[SelfEvolutionChange]:
        """Create a change-set from one or more proposed diffs.

        The run fires only on a user-originated trigger (HL-TRUST-21); an
        assistant/untrusted trigger cannot itself start a self-evolution run.
        """
        if str(trigger or "").strip().lower() != "user":
            raise SelfEvolutionError(
                "self-evolution runs fire only on a user-originated trigger; "
                f"trigger {trigger!r} is not permitted"
            )
        changeset_id = uuid_text()
        rows: list[SelfEvolutionChange] = []
        for change in changes:
            category = change.normalized_category()
            risk_class, risk_reason = classify_diff(category, change.target_path, change.unified_diff)
            trust_level = stamp_trust_level(change.origin_trust, change.justification_trust)
            review_inbox = risk_class == REVIEW_REQUIRED or is_untrusted(trust_level)
            row = SelfEvolutionChange(
                project_id=project_id,
                run_id=run_id,
                changeset_id=changeset_id,
                change_id=uuid_text(),
                category=category,
                target_path=change.target_path,
                unified_diff=self.redact(change.unified_diff),
                new_content=change.new_content,
                test_plan=json.dumps(list(change.test_plan or [])),
                risk_class=risk_class,
                risk_reason=risk_reason,
                trust_level=trust_level,
                origin=change.origin,
                status=STATUS_PROPOSED,
                review_inbox=review_inbox,
            )
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
            await self._audit(row, action=ACTION_PROPOSED, approval_state=STATUS_PROPOSED, actor=actor)
            rows.append(row)
        return rows

    async def list_changes(self, *, project_id: str) -> list[SelfEvolutionChange]:
        result = await self.session.exec(
            select(SelfEvolutionChange)
            .where(SelfEvolutionChange.project_id == project_id)
            .order_by(SelfEvolutionChange.created_at.desc())
        )
        return list(result.all())

    async def get(self, change_id: str) -> SelfEvolutionChange | None:
        result = await self.session.exec(
            select(SelfEvolutionChange).where(SelfEvolutionChange.change_id == change_id)
        )
        return result.first()

    async def _touch(self, row: SelfEvolutionChange) -> None:
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)

    # -- deny ----------------------------------------------------------------
    async def deny(self, change_id: str, *, actor: str = "user") -> SelfEvolutionChange:
        row = await self._require(change_id)
        if row.status not in {STATUS_PROPOSED, STATUS_APPROVED}:
            raise SelfEvolutionError(f"change {change_id} is {row.status} and cannot be denied")
        row.status = STATUS_DENIED
        await self._touch(row)
        await self._audit(row, action=ACTION_DENIED, approval_state=STATUS_DENIED, actor=actor)
        return row

    # -- approve → checkpoint → apply → verify → keep|rollback ---------------
    async def approve(self, change_id: str, *, actor: str = "user") -> SelfEvolutionChange:
        row = await self._require(change_id)
        if row.status != STATUS_PROPOSED:
            raise SelfEvolutionError(f"change {change_id} is {row.status}; only a proposed change can be approved")

        # Trust gate: untrusted-traced proposals never reach the apply path.
        if is_untrusted(row.trust_level):
            row.review_inbox = True
            await self._touch(row)
            raise SelfEvolutionError(
                "untrusted-external proposals route to the Review Inbox and cannot be applied"
            )

        # Protected-field gate: review_required never auto-applies, even Full Access.
        if row.risk_class == REVIEW_REQUIRED:
            row.review_inbox = True
            await self._touch(row)
            raise SelfEvolutionError(
                f"change touches a protected target ({row.risk_reason}); it routes to the "
                "Review Inbox and cannot be auto-applied"
            )

        # A change with no valid test plan is not approvable (HL-ASSIST-31).
        try:
            test_plan = validate_test_plan(json.loads(row.test_plan or "[]"))
        except TestPlanError as exc:
            raise SelfEvolutionError(str(exc)) from exc

        # Explicit per-change approval recorded before any disk mutation.
        row.status = STATUS_APPROVED
        await self._touch(row)
        await self._audit(row, action=ACTION_APPROVED, approval_state=STATUS_APPROVED, actor=actor)

        # Checkpoint MUST precede the write; abort (no write) if it fails.
        try:
            checkpoint = await self.checkpoints.create(
                project_id=row.project_id,
                run_id=row.run_id,
                label=f"self-evolution {row.change_id}",
                target=row.target_path,
            )
        except CheckpointError as exc:
            await self._audit(
                row, action=ACTION_CHECKPOINT_FAILED, approval_state="checkpoint_failed", actor=actor
            )
            raise SelfEvolutionError(f"checkpoint failed; apply aborted with no write: {exc}") from exc

        row.checkpoint_ref = checkpoint.commit or checkpoint.git_ref
        await self._touch(row)

        # Apply: write the payload to disk (contained within the project root).
        self._write_target(row)
        await self._audit(row, action=ACTION_APPLIED, approval_state=STATUS_APPLIED, actor=actor)

        # Auto-verify through the fixed allowlist runner.
        outcome: VerificationOutcome = self.verifier.run(test_plan)
        if outcome.passed:
            row.status = STATUS_APPLIED
            row.verification_result = "pass"
            await self._touch(row)
            await self._audit(row, action=ACTION_VERIFIED, approval_state="pass", actor="assistant")
            return row

        # Failure: restore the pre-apply checkpoint → byte-identical tree.
        self.checkpoints.restore(row.target_path, ref=str(row.checkpoint_ref or "HEAD"))
        row.status = STATUS_ROLLED_BACK
        row.verification_result = "fail"
        await self._touch(row)
        await self._audit(row, action=ACTION_VERIFIED, approval_state="fail", actor="assistant")
        await self._audit(row, action=ACTION_ROLLED_BACK, approval_state=STATUS_ROLLED_BACK, actor="assistant")
        return row

    # -- internals -----------------------------------------------------------
    async def _require(self, change_id: str) -> SelfEvolutionChange:
        row = await self.get(change_id)
        if row is None:
            raise SelfEvolutionError(f"change {change_id} not found")
        return row

    def _write_target(self, row: SelfEvolutionChange) -> None:
        target = (self.project_root / row.target_path).resolve()
        if not str(target).startswith(str(self.project_root)):
            raise SelfEvolutionError("target path escapes the project root; refusing to write")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(row.new_content, encoding="utf-8")
