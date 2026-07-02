"""Append-only autonomy audit ledger."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import AgentAuditLedgerEntry

# Defense-in-depth beyond the append-only Python API: SQLite triggers that abort
# any UPDATE/DELETE on prior rows so the forensic ledger cannot be rewritten by
# another code path or a direct ORM mutation (HL-MODE-35, L2).
LEDGER_APPEND_ONLY_TRIGGERS: tuple[str, ...] = (
    "CREATE TRIGGER IF NOT EXISTS agent_audit_ledger_no_update "
    "BEFORE UPDATE ON agent_audit_ledger "
    "BEGIN SELECT RAISE(ABORT, 'audit ledger is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS agent_audit_ledger_no_delete "
    "BEFORE DELETE ON agent_audit_ledger "
    "BEGIN SELECT RAISE(ABORT, 'audit ledger is append-only'); END",
)

class AuditLedger:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(
        self,
        *,
        project_id: str,
        run_id: str | None,
        actor: str,
        action: str,
        risk_level: str,
        target: str,
        approval_state: str,
    ) -> AgentAuditLedgerEntry:
        entry = AgentAuditLedgerEntry(
            project_id=project_id,
            run_id=run_id,
            actor=actor,
            action=action,
            risk_level=risk_level,
            target=target,
            approval_state=approval_state,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def list(self, *, project_id: str, run_id: str | None = None) -> list[AgentAuditLedgerEntry]:
        query = select(AgentAuditLedgerEntry).where(AgentAuditLedgerEntry.project_id == project_id)
        if run_id:
            query = query.where(AgentAuditLedgerEntry.run_id == run_id)
        res = await self.session.exec(query.order_by(AgentAuditLedgerEntry.created_at.asc()))
        return list(res.all())
