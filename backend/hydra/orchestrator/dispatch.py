"""Access-mode dispatch guard for stage write/send/tool actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.approvals import ApprovalService
from hydra.agents.policy import (
    FULL_ACCESS_EXCLUDED_ACTIONS,
    Outcome,
    PolicyDecision,
    WriteRequest,
    evaluate_write,
)
from hydra.database.repository import Repository
from hydra.services.assistant.consent import SendScopeItem, resolve_send_scope


@dataclass
class PrivacyPosture:
    g3_enabled: bool = False
    offline_only: bool = False
    opt_ins: dict[str, bool] = field(default_factory=dict)
    ignored_paths: list[str] = field(default_factory=list)
    egress_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DispatchAction:
    mode: str
    action_kind: str
    target_kind: str | None = None
    target_ref: str | None = None
    risk_level: str = "low"
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


@dataclass
class DispatchResult:
    decision: PolicyDecision
    applied: bool = False
    status: str = "queued"
    reason: str = ""
    review_item_id: str | None = None
    approval_id: str | None = None


class DispatchGuard:
    """Single orchestrator guard for writes, provider sends, and tool calls."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def dispatch(self, action: DispatchAction) -> DispatchResult:
        offline = self._offline_decision(action)
        if offline is not None:
            return offline

        decision = evaluate_write(
            WriteRequest(
                mode=action.mode,
                action_kind=action.action_kind,
                target_kind=action.target_kind,
                target_ref=action.target_ref,
                risk_level=action.risk_level,
                trust_origin=action.trust_origin,
                justification_trust=action.justification_trust,
                capability=action.capability,
                high_risk_category=action.high_risk_category,
                full_access_enabled=action.full_access_enabled,
            )
        )

        if decision.outcome == Outcome.APPLY.value:
            return DispatchResult(decision=decision, applied=True, status="applied", reason=decision.reason)

        if decision.outcome == Outcome.BLOCKED.value:
            return DispatchResult(decision=decision, applied=False, status="blocked", reason=decision.reason)

        hard_exclusion_requires_approval = (
            decision.outcome == Outcome.REVIEW_INBOX.value
            and action.action_kind in FULL_ACCESS_EXCLUDED_ACTIONS
        )
        if hard_exclusion_requires_approval:
            decision = PolicyDecision(
                outcome=Outcome.APPROVAL_REQUIRED.value,
                reason=decision.reason,
                logged=decision.logged,
                checkpoint_required=decision.checkpoint_required,
                review_inbox=False,
                metadata=decision.metadata,
            )

        if decision.outcome == Outcome.REVIEW_INBOX.value or action.mode == "passive":
            item = await Repository(self.session).create_review_item(
                {
                    "project_id": action.project_id,
                    "item_type": "agent-stage-proposal",
                    "title": action.summary or f"Review {action.action_kind}",
                    "summary": decision.reason,
                    "origin_type": "agent_run",
                    "origin_id": action.run_id,
                    "target_type": action.target_kind,
                    "target_id": action.target_ref,
                    "payload": {
                        "action_kind": action.action_kind,
                        "trust_origin": action.trust_origin,
                        "justification_trust": action.justification_trust,
                        "decision": decision.outcome,
                        **action.payload,
                    },
                }
            )
            return DispatchResult(
                decision=PolicyDecision(
                    outcome=Outcome.REVIEW_INBOX.value,
                    reason=decision.reason,
                    logged=decision.logged,
                    review_inbox=True,
                    metadata=decision.metadata,
                ),
                applied=False,
                status="review_inbox",
                reason=decision.reason,
                review_item_id=item["id"],
            )

        approval = await ApprovalService(self.session).request(
            action_kind=action.action_kind,
            summary=action.summary or decision.reason,
            mode=action.mode,
            run_id=action.run_id,
            project_id=action.project_id,
            target_kind=action.target_kind,
            target_ref=action.target_ref,
            trust_origin=action.trust_origin,
            reason=decision.reason,
            payload=action.payload,
        )
        return DispatchResult(
            decision=decision,
            applied=False,
            status="approval_required",
            reason=decision.reason,
            approval_id=approval.id,
        )

    def _offline_decision(self, action: DispatchAction) -> DispatchResult | None:
        if action.action_kind not in {"provider_send", "tool_call"}:
            return None
        privacy = action.privacy or PrivacyPosture()
        items = [
            SendScopeItem(
                ref_type=str(item.get("type") or item.get("ref_type") or "attachment"),
                id_or_path=str(item.get("id_or_path") or item.get("id") or ""),
                locator=dict(item.get("locator") or {}),
                label=str(item.get("label") or item.get("id_or_path") or ""),
            )
            for item in privacy.egress_items
        ]
        scope = resolve_send_scope(
            items,
            g3_enabled=privacy.g3_enabled,
            offline_only=privacy.offline_only,
            opt_ins=privacy.opt_ins,
            ignored_paths=privacy.ignored_paths,
        )
        if privacy.offline_only and scope.excluded:
            return DispatchResult(
                decision=PolicyDecision(
                    outcome=Outcome.BLOCKED.value,
                    reason="permission denied (offline)",
                    logged=True,
                    metadata={"blocked_by": "offline_only"},
                ),
                applied=False,
                status="permission-denied",
                reason="permission denied (offline)",
            )
        if scope.has_hard_block:
            return DispatchResult(
                decision=PolicyDecision(
                    outcome=Outcome.BLOCKED.value,
                    reason=str(scope.blocked[0].get("reason") or "hard-blocked category"),
                    logged=True,
                ),
                applied=False,
                status="permission-denied",
                reason=str(scope.blocked[0].get("reason") or "hard-blocked category"),
            )
        return None
