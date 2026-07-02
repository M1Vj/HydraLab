"""Read-only reproducibility export over the append-only autonomy ledger."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.autonomy.audit import AuditLedger
from hydra.database.models import AgentApproval, AgentCheckpoint, AgentRun


@dataclass(frozen=True)
class RunLedgerExport:
    run_id: str
    entries: list[dict[str, Any]] = field(default_factory=list)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    trust_decisions: list[dict[str, Any]] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "entries": [dict(item) for item in self.entries],
            "approvals": [dict(item) for item in self.approvals],
            "checkpoints": [dict(item) for item in self.checkpoints],
            "trust_decisions": [dict(item) for item in self.trust_decisions],
        }


@dataclass(frozen=True)
class LedgerExport:
    project_id: str
    runs: list[RunLedgerExport] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        return {"project_id": self.project_id, "runs": [run.public_dict() for run in self.runs]}


async def export_run_ledger(session: AsyncSession, *, project_id: str, run_ids: list[str]) -> LedgerExport:
    runs: list[RunLedgerExport] = []
    ledger = AuditLedger(session)
    for run_id in run_ids:
        entries = [_entry(row) for row in await ledger.list(project_id=project_id, run_id=run_id)]
        approvals = await _approvals(session, project_id=project_id, run_id=run_id)
        checkpoints = await _checkpoints(session, project_id=project_id, run_id=run_id)
        run = await session.get(AgentRun, run_id)
        runs.append(
            RunLedgerExport(
                run_id=run_id,
                entries=entries,
                approvals=approvals,
                checkpoints=checkpoints,
                trust_decisions=_parse_json_list(run.trust_decisions if run else "[]"),
            )
        )
    return LedgerExport(project_id=project_id, runs=runs)


def _entry(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "run_id": row.run_id,
        "actor": row.actor,
        "action": row.action,
        "risk_level": row.risk_level,
        "target": row.target,
        "approval_state": row.approval_state,
        "created_at": row.created_at.isoformat(),
    }


async def _approvals(session: AsyncSession, *, project_id: str, run_id: str) -> list[dict[str, Any]]:
    result = await session.exec(
        select(AgentApproval)
        .where(AgentApproval.project_id == project_id)
        .where(AgentApproval.run_id == run_id)
        .order_by(AgentApproval.created_at.asc())
    )
    return [
        {
            "id": row.id,
            "mode": row.mode,
            "action_kind": row.action_kind,
            "target_kind": row.target_kind,
            "target_ref": row.target_ref,
            "summary": row.summary,
            "status": row.status,
            "decision": row.decision,
            "reason": row.reason,
            "trust_origin": row.trust_origin,
            "created_at": row.created_at.isoformat(),
        }
        for row in result.all()
    ]


async def _checkpoints(session: AsyncSession, *, project_id: str, run_id: str) -> list[dict[str, Any]]:
    result = await session.exec(
        select(AgentCheckpoint)
        .where(AgentCheckpoint.project_id == project_id)
        .where(AgentCheckpoint.run_id == run_id)
        .order_by(AgentCheckpoint.created_at.asc())
    )
    return [
        {
            "id": row.id,
            "git_ref": row.git_ref,
            "commit": row.commit,
            "label": row.label,
            "target": row.target,
            "created_at": row.created_at.isoformat(),
        }
        for row in result.all()
    ]


def _parse_json_list(value: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [dict(item) for item in parsed if isinstance(item, dict)]
