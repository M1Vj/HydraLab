"""Collaboration transport boundary."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.collaboration.exclusion import DocumentCandidate, SyncExclusionFilter
from hydra.collaboration.identity import CollaborationPermissionError, IdentityProvider
from hydra.database.models import CollaboratorIdentity

ALLOWED_WS_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:5176",
    "http://127.0.0.1:5176",
    "http://localhost:5177",
    "http://127.0.0.1:5177",
    "http://localhost:5178",
    "http://127.0.0.1:5178",
    "http://localhost:5179",
    "http://127.0.0.1:5179",
}


class SyncAuthenticationError(PermissionError):
    """Raised before any document bytes leave the server."""


class SyncTransport(Protocol):
    kind: str


@dataclass
class SelfHostedSyncTransport:
    url: str
    kind: str = "self-hosted"

    def __post_init__(self) -> None:
        if not self.url.startswith("wss://"):
            raise ValueError("self-hosted collaboration sync requires a wss:// URL")


@dataclass
class HostedSyncTransportAdapter:
    """Unused extension point; hosted sync is not a Phase-3 dependency."""

    url: str
    kind: str = "hosted-adapter-unused"

    def __post_init__(self) -> None:
        raise RuntimeError("hosted collaboration sync is not available in Phase 3")


@dataclass
class SyncConnection:
    project_id: str
    document_id: str
    collaborator_id: str
    display_name: str
    permission: str
    connected_at: float
    connected: bool = True
    disconnected_after_seconds: float = 0

    def disconnect(self) -> None:
        if not self.connected:
            return
        self.connected = False
        self.disconnected_after_seconds = min(time.monotonic() - self.connected_at, 5)


class InProcessSyncTransport:
    """Deterministic test transport that records bytes crossing the boundary."""

    kind = "self-hosted"

    def __init__(self) -> None:
        self.bytes_sent: list[bytes] = []
        self.connection_attempts = 0
        self.connections: list[SyncConnection] = []
        self.documents: dict[str, bytes] = {}

    def seed_document(self, document_id: str, content: bytes) -> None:
        self.documents[document_id] = content

    async def connect(
        self,
        session: AsyncSession,
        *,
        project_id: str,
        document_id: str,
        auth_token: str | None,
        origin: str | None,
    ) -> SyncConnection:
        self.connection_attempts += 1
        if not validate_ws_origin(origin):
            raise SyncAuthenticationError("forbidden collaboration websocket origin")
        try:
            auth = await IdentityProvider(session).authenticate_session_token(project_id=project_id, session_token=auth_token)
        except CollaborationPermissionError as exc:
            raise SyncAuthenticationError(str(exc)) from exc
        connection = SyncConnection(
            project_id=project_id,
            document_id=document_id,
            collaborator_id=auth.collaborator_id,
            display_name=auth.display_name,
            permission=auth.permission,
            connected_at=time.monotonic(),
        )
        self.connections.append(connection)
        return connection

    async def disconnect_revoked(self, session: AsyncSession) -> int:
        disconnected = 0
        identity = IdentityProvider(session)
        for connection in self.connections:
            if not connection.connected:
                continue
            try:
                await identity.authenticate_session_token(project_id=connection.project_id, session_token="")
            except CollaborationPermissionError:
                pass
            collaborator = await session.get(CollaboratorIdentity, connection.collaborator_id)
            if collaborator is not None and collaborator.revoked_at is not None:
                connection.disconnect()
                disconnected += 1
        return disconnected

    def send_if_allowed(self, candidate: DocumentCandidate, filter_: SyncExclusionFilter) -> bool:
        payload = filter_.serialize(candidate)
        if payload is None:
            return False
        self.bytes_sent.append(payload)
        return True


def validate_ws_origin(origin: str | None) -> bool:
    return origin in ALLOWED_WS_ORIGINS
