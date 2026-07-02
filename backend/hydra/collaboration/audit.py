"""Append-only collaborative edit audit trail."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import CollaborativeEditAuditEntry

COLLABORATION_AUDIT_APPEND_ONLY_TRIGGERS: tuple[str, ...] = (
    "CREATE TRIGGER IF NOT EXISTS collaborative_edit_audit_no_update "
    "BEFORE UPDATE ON collaborative_edit_audit "
    "BEGIN SELECT RAISE(ABORT, 'collaborative edit audit is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS collaborative_edit_audit_no_delete "
    "BEFORE DELETE ON collaborative_edit_audit "
    "BEGIN SELECT RAISE(ABORT, 'collaborative edit audit is append-only'); END",
)


class CollaborativeAuditTrail:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(
        self,
        *,
        project_id: str,
        collaborator_id: str,
        document_id: str,
        change_summary: str,
    ) -> CollaborativeEditAuditEntry:
        row = CollaborativeEditAuditEntry(
            project_id=project_id,
            collaborator_id=collaborator_id,
            document_id=document_id,
            change_summary=change_summary,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list(self, *, project_id: str, document_id: str | None = None) -> list[CollaborativeEditAuditEntry]:
        query = select(CollaborativeEditAuditEntry).where(CollaborativeEditAuditEntry.project_id == project_id)
        if document_id:
            query = query.where(CollaborativeEditAuditEntry.document_id == document_id)
        result = await self.session.exec(query.order_by(CollaborativeEditAuditEntry.created_at.asc()))
        return list(result.all())

