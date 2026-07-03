"""Durable collaboration document state and live peer broadcast.

Two collaborators editing the same note must see each other's changes and must
not lose them across a reconnect or backend restart. The server stores the
ordered Yjs update log (``CollaborationDocumentStore``) and replays it to a
joining client, and fans out each live update to the document's other sockets
(``CollaborationRooms``). No CRDT engine runs server-side — Yjs merges the
replayed and live updates on the client.
"""
from __future__ import annotations

from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import CollaborationUpdate


class CollaborationDocumentStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append_update(self, *, project_id: str, document_id: str, update_b64: str) -> CollaborationUpdate:
        last = (
            await self.session.exec(
                select(CollaborationUpdate.seq)
                .where(
                    CollaborationUpdate.project_id == project_id,
                    CollaborationUpdate.document_id == document_id,
                )
                .order_by(CollaborationUpdate.seq.desc())
            )
        ).first()
        row = CollaborationUpdate(
            project_id=project_id,
            document_id=document_id,
            seq=(last or 0) + 1,
            update_b64=update_b64,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def load_updates(self, *, project_id: str, document_id: str) -> list[str]:
        rows = (
            await self.session.exec(
                select(CollaborationUpdate)
                .where(
                    CollaborationUpdate.project_id == project_id,
                    CollaborationUpdate.document_id == document_id,
                )
                .order_by(CollaborationUpdate.seq.asc())
            )
        ).all()
        return [row.update_b64 for row in rows]


class CollaborationRooms:
    """In-process registry of live document sockets for peer broadcast."""

    def __init__(self) -> None:
        self._rooms: dict[tuple[str, str], set[Any]] = {}

    def join(self, project_id: str, document_id: str, member: Any) -> None:
        self._rooms.setdefault((project_id, document_id), set()).add(member)

    def leave(self, project_id: str, document_id: str, member: Any) -> None:
        room = self._rooms.get((project_id, document_id))
        if room is None:
            return
        room.discard(member)
        if not room:
            self._rooms.pop((project_id, document_id), None)

    def peers(self, project_id: str, document_id: str, sender: Any) -> list[Any]:
        return [member for member in self._rooms.get((project_id, document_id), set()) if member is not sender]

    async def broadcast(self, project_id: str, document_id: str, message: str, *, sender: Any) -> int:
        delivered = 0
        for member in self.peers(project_id, document_id, sender):
            try:
                await member.send_text(message)
                delivered += 1
            except Exception:
                # A dead peer is skipped; its own handler prunes it on disconnect.
                pass
        return delivered
