"""Autonomy action gate: classify, audit/checkpoint, then delegate to DispatchGuard."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.contracts import ApprovalStatus
from hydra.agents.policy import Outcome
from hydra.autonomy.audit import AuditLedger
from hydra.autonomy.checkpoints import CheckpointService
from hydra.autonomy.risk import RiskClassifier
from hydra.database.models import AgentApproval
from hydra.orchestrator.dispatch import DispatchAction, DispatchGuard, PrivacyPosture

ApplyFn = Callable[[], Awaitable[Any]]

@dataclass
class GovernedAction:
    mode: str
    action_kind: str
    target_kind: str | None = None
    target_ref: str | None = None
    trust_origin: str = "user"
    justification_trust: str = "user"
    capability: str | None = None
    high_risk_category: str | None = None
    full_access_enabled: bool = False
    run_id: str | None = None
    project_id: str = "default"
    summary: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    privacy: PrivacyPosture | None = None
    actor: str = "autopilot"
    # Apply-after-approval is proven ONLY by a persisted, approved AgentApproval
    # row id — never a caller-supplied bool (see govern()).
    approval_id: str | None = None
    # Optional side-effect callback governed actions run once, after the gate
    # authorises apply and (for high-risk) a checkpoint exists.
    apply_fn: ApplyFn | None = None

@dataclass
class GateResult:
    status: str
    applied: bool
    risk_level: str
    reason: str
    audit_id: str
    checkpoint_id: str | None = None
    review_item_id: str | None = None
    approval_id: str | None = None

class ActionGate:
    def __init__(
        self,
        session: AsyncSession,
        *,
        classifier: RiskClassifier | None = None,
        guard: DispatchGuard | None = None,
        checkpoints: CheckpointService | None = None,
        audit: AuditLedger | None = None,
    ) -> None:
        self.session = session
        self.classifier = classifier or RiskClassifier()
        self.guard = guard or DispatchGuard(session)
        self.checkpoints = checkpoints or CheckpointService(session)
        self.audit = audit or AuditLedger(session)

    async def govern(self, action: GovernedAction, apply_fn: ApplyFn | None = None) -> GateResult:
        risk = self.classifier.classify(action)
        dispatch = await self.guard.dispatch(
            DispatchAction(
                mode=action.mode,
                action_kind=action.action_kind,
                target_kind=action.target_kind,
                target_ref=action.target_ref,
                risk_level=risk,
                trust_origin=action.trust_origin,
                justification_trust=action.justification_trust,
                capability=action.capability,
                high_risk_category=action.high_risk_category,
                full_access_enabled=action.full_access_enabled,
                run_id=action.run_id,
                project_id=action.project_id,
                summary=action.summary,
                payload=self._payload(action, risk),
                privacy=action.privacy,
            )
        )
        target = action.target_ref or action.target_kind or ""

        # Only the chokepoint's own APPLY outcome auto-applies. A human approval
        # is honoured ONLY through a persisted, approved AgentApproval row whose
        # project/action_kind/target match — an inbound bool is never trusted (H1).
        # The row is CONSUMED on use so a single approval cannot be replayed
        # across loop iterations.
        should_apply = dispatch.applied
        if not should_apply and action.approval_id and dispatch.status == "approval_required":
            should_apply = await self._consume_approval(action)

        checkpoint_id: str | None = None
        if should_apply:
            if risk == "high" or dispatch.decision.checkpoint_required:
                checkpoint = await self.checkpoints.create(
                    project_id=action.project_id,
                    run_id=action.run_id,
                    label=f"before {action.action_kind}",
                    target=target,
                )
                checkpoint_id = checkpoint.id
            runner = apply_fn or action.apply_fn
            if runner is not None:
                await runner()
            # Audit is written AFTER a successful checkpoint + apply so the ledger
            # never records "applied" for an action that a CheckpointError aborted.
            audit = await self.audit.append(
                project_id=action.project_id,
                run_id=action.run_id,
                actor=action.actor,
                action=action.action_kind,
                risk_level=risk,
                target=target,
                approval_state="applied",
            )
            return GateResult(
                status="applied",
                applied=True,
                risk_level=risk,
                reason=dispatch.reason,
                audit_id=audit.id,
                checkpoint_id=checkpoint_id,
                review_item_id=dispatch.review_item_id,
                approval_id=dispatch.approval_id,
            )

        approval_state = "blocked" if dispatch.decision.outcome == Outcome.BLOCKED.value else dispatch.status
        audit = await self.audit.append(
            project_id=action.project_id,
            run_id=action.run_id,
            actor=action.actor,
            action=action.action_kind,
            risk_level=risk,
            target=target,
            approval_state=approval_state,
        )
        return GateResult(
            status=dispatch.status,
            applied=False,
            risk_level=risk,
            reason=dispatch.reason,
            audit_id=audit.id,
            checkpoint_id=checkpoint_id,
            review_item_id=dispatch.review_item_id,
            approval_id=dispatch.approval_id,
        )

    async def _consume_approval(self, action: GovernedAction) -> bool:
        approval = await self.session.get(AgentApproval, action.approval_id)
        authorised = (
            approval is not None
            and approval.status == ApprovalStatus.APPROVED.value
            and approval.action_kind == action.action_kind
            and (approval.target_ref or None) == (action.target_ref or None)
            and (approval.project_id or None) in (None, action.project_id)
        )
        if authorised:
            # Consume: a used approval can never authorise a second apply.
            approval.status = "consumed"
            approval.decision = "applied"
            self.session.add(approval)
            await self.session.commit()
        return authorised

    def _payload(self, action: GovernedAction, risk: str) -> dict[str, Any]:
        payload = dict(action.payload)
        payload.setdefault("risk_level", risk)
        if action.trust_origin == "untrusted-external" or action.justification_trust == "untrusted-external":
            payload.setdefault("tag", "untrusted-external")
        return payload
