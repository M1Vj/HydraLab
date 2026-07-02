"""Autonomy action gate: classify, audit/checkpoint, then delegate to DispatchGuard."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.policy import Outcome
from hydra.autonomy.audit import AuditLedger
from hydra.autonomy.checkpoints import CheckpointService
from hydra.autonomy.risk import RiskClassifier
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
    approved: bool = False

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
        approval_state = dispatch.status
        if dispatch.decision.outcome == Outcome.BLOCKED.value:
            approval_state = "blocked"

        audit = await self.audit.append(
            project_id=action.project_id,
            run_id=action.run_id,
            actor=action.actor,
            action=action.action_kind,
            risk_level=risk,
            target=target,
            approval_state=approval_state,
        )

        checkpoint_id: str | None = None
        should_apply = dispatch.applied or (action.approved and dispatch.status == "approval_required")
        if should_apply:
            if risk == "high" or dispatch.decision.checkpoint_required:
                checkpoint = await self.checkpoints.create(
                    project_id=action.project_id,
                    run_id=action.run_id,
                    label=f"before {action.action_kind}",
                    target=target,
                )
                checkpoint_id = checkpoint.id
            if apply_fn is not None:
                await apply_fn()
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

    def _payload(self, action: GovernedAction, risk: str) -> dict[str, Any]:
        payload = dict(action.payload)
        payload.setdefault("risk_level", risk)
        if action.trust_origin == "untrusted-external" or action.justification_trust == "untrusted-external":
            payload.setdefault("tag", "untrusted-external")
        return payload
