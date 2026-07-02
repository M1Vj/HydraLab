"""Co-pilot per-item approval model and Full-Access downgrade recording.

In Co-pilot mode each substantive write is presented as an approval item the
researcher accepts or rejects one-by-one (HL-MODE-02). Rejecting an approval
mutates NO workspace state — the apply callback runs only on ``approved``.
Full-Access exclusions (Section 29.6) are recorded here as downgraded approval
items so they land in the Review Inbox with a logged reason (HL-MODE-05).

No agent framework is imported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.contracts import Approval, ApprovalStatus
from hydra.database.models import AgentApproval


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ApplyResult:
    applied: bool
    status: str
    reason: str = ""


class ApprovalService:
    """Persists and resolves per-item approvals."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def request(
        self,
        *,
        action_kind: str,
        summary: str = "",
        mode: str = "copilot",
        run_id: Optional[str] = None,
        project_id: Optional[str] = None,
        target_kind: Optional[str] = None,
        target_ref: Optional[str] = None,
        trust_origin: str = "user",
        reason: str = "",
        payload: Optional[dict[str, Any]] = None,
    ) -> AgentApproval:
        approval = AgentApproval(
            run_id=run_id,
            project_id=project_id,
            mode=mode,
            action_kind=action_kind,
            summary=summary,
            target_kind=target_kind,
            target_ref=target_ref,
            trust_origin=trust_origin,
            reason=reason,
            status=ApprovalStatus.PENDING.value,
            payload_json=json.dumps(payload or {}, sort_keys=True),
        )
        self.session.add(approval)
        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def resolve(
        self,
        approval_id: str,
        *,
        decision: str,
        apply_fn: Optional[Callable[[], Awaitable[Any]]] = None,
    ) -> ApplyResult:
        """Resolve an approval. The apply callback runs ONLY on ``approved``.

        On reject, ``apply_fn`` is never invoked, so no file, SQLite row, sidecar
        or context file changes (HL-MODE-02).
        """

        approval = await self.session.get(AgentApproval, approval_id)
        if approval is None:
            return ApplyResult(applied=False, status="missing", reason="approval not found")

        normalized = str(decision or "").strip().lower()
        if normalized in {"approve", "approved", "accept", "accepted"}:
            if apply_fn is not None:
                await apply_fn()
            approval.status = ApprovalStatus.APPROVED.value
            approval.decision = "approved"
            approval.updated_at = _utcnow()
            self.session.add(approval)
            await self.session.commit()
            return ApplyResult(applied=True, status=ApprovalStatus.APPROVED.value)

        # Any non-approval decision rejects and mutates nothing.
        approval.status = ApprovalStatus.REJECTED.value
        approval.decision = "rejected"
        approval.updated_at = _utcnow()
        self.session.add(approval)
        await self.session.commit()
        return ApplyResult(applied=False, status=ApprovalStatus.REJECTED.value)

    async def list_pending(self, project_id: Optional[str] = None) -> list[AgentApproval]:
        query = select(AgentApproval).where(AgentApproval.status == ApprovalStatus.PENDING.value)
        if project_id:
            query = query.where(AgentApproval.project_id == project_id)
        res = await self.session.exec(query.order_by(AgentApproval.created_at.asc()))
        return list(res.all())

    async def get(self, approval_id: str) -> Optional[AgentApproval]:
        return await self.session.get(AgentApproval, approval_id)


def to_contract(row: AgentApproval) -> Approval:
    return Approval(
        id=row.id,
        action_kind=row.action_kind,
        status=row.status,
        decision=row.decision,
        reason=row.reason,
        trust_origin=row.trust_origin,
        target_kind=row.target_kind,
        target_ref=row.target_ref,
        summary=row.summary,
    )
