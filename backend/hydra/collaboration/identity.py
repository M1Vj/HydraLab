"""Collaborator identity, invitation and revocation service."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import CollaboratorIdentity, ProjectCollaborationPermission, ProjectCollaborationSettings

COLLABORATION_PERMISSIONS = ("read", "comment", "edit")


class CollaborationPermissionError(ValueError):
    """Raised when a collaboration permission or credential is invalid."""


@dataclass(frozen=True)
class InviteResult:
    collaborator_id: str
    invite_token: str
    permission: str


@dataclass(frozen=True)
class AuthenticatedCollaborator:
    collaborator_id: str
    display_name: str
    permission: str
    session_token: str


class IdentityProvider:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def set_project_settings(self, *, project_id: str, enabled: bool, sync_server_url: str = "") -> ProjectCollaborationSettings:
        row = await self.session.get(ProjectCollaborationSettings, project_id)
        if row is None:
            row = ProjectCollaborationSettings(project_id=project_id)
        row.enabled = bool(enabled)
        row.sync_server_url = sync_server_url
        row.sync_server_kind = "self-hosted"
        row.updated_at = _utcnow()
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def settings(self, project_id: str) -> ProjectCollaborationSettings:
        row = await self.session.get(ProjectCollaborationSettings, project_id)
        if row is not None:
            return row
        return ProjectCollaborationSettings(project_id=project_id, enabled=False)

    async def invite(self, *, project_id: str, display_name: str, permission: str) -> InviteResult:
        permission = _normalize_permission(permission)
        invite_token = secrets.token_urlsafe(32)
        collaborator = CollaboratorIdentity(display_name=display_name)
        self.session.add(collaborator)
        await self.session.flush()
        row = ProjectCollaborationPermission(
            project_id=project_id,
            collaborator_id=collaborator.id,
            permission=permission,
            invite_token_hash=_hash_token(invite_token),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(collaborator)
        return InviteResult(collaborator_id=collaborator.id, invite_token=invite_token, permission=permission)

    async def authenticate(self, *, project_id: str, invite_token: str) -> AuthenticatedCollaborator:
        token_hash = _hash_token(invite_token)
        permission = await self._permission_by_invite(project_id, token_hash)
        if permission is None or permission.revoked_at is not None:
            raise CollaborationPermissionError("collaborator invite is invalid or revoked")
        collaborator = await self.session.get(CollaboratorIdentity, permission.collaborator_id)
        if collaborator is None or collaborator.revoked_at is not None:
            raise CollaborationPermissionError("collaborator identity is revoked")
        session_token = secrets.token_urlsafe(32)
        collaborator.auth_token_hash = _hash_token(session_token)
        permission.authenticated_at = _utcnow()
        self.session.add(collaborator)
        self.session.add(permission)
        await self.session.commit()
        return AuthenticatedCollaborator(
            collaborator_id=collaborator.id,
            display_name=collaborator.display_name,
            permission=permission.permission,
            session_token=session_token,
        )

    async def authenticate_session_token(self, *, project_id: str, session_token: str | None) -> AuthenticatedCollaborator:
        if not session_token:
            raise CollaborationPermissionError("missing collaboration credentials")
        token_hash = _hash_token(session_token)
        query = (
            select(ProjectCollaborationPermission, CollaboratorIdentity)
            .where(ProjectCollaborationPermission.project_id == project_id)
            .where(ProjectCollaborationPermission.collaborator_id == CollaboratorIdentity.id)
            .where(CollaboratorIdentity.auth_token_hash == token_hash)
        )
        result = (await self.session.exec(query)).first()
        if result is None:
            raise CollaborationPermissionError("invalid collaboration credentials")
        permission, collaborator = result
        if permission.revoked_at is not None or collaborator.revoked_at is not None:
            raise CollaborationPermissionError("collaborator access is revoked")
        return AuthenticatedCollaborator(
            collaborator_id=collaborator.id,
            display_name=collaborator.display_name,
            permission=permission.permission,
            session_token=session_token,
        )

    async def revoke(self, *, project_id: str, collaborator_id: str) -> None:
        now = _utcnow()
        collaborator = await self.session.get(CollaboratorIdentity, collaborator_id)
        if collaborator is not None:
            collaborator.revoked_at = now
            self.session.add(collaborator)
        query = (
            select(ProjectCollaborationPermission)
            .where(ProjectCollaborationPermission.project_id == project_id)
            .where(ProjectCollaborationPermission.collaborator_id == collaborator_id)
            .where(ProjectCollaborationPermission.revoked_at.is_(None))
        )
        for permission in (await self.session.exec(query)).all():
            permission.revoked_at = now
            self.session.add(permission)
        await self.session.commit()

    async def list_collaborators(self, project_id: str) -> list[dict[str, object]]:
        query = (
            select(ProjectCollaborationPermission, CollaboratorIdentity)
            .where(ProjectCollaborationPermission.project_id == project_id)
            .where(ProjectCollaborationPermission.collaborator_id == CollaboratorIdentity.id)
        )
        rows = (await self.session.exec(query)).all()
        return [
            {
                "collaborator_id": identity.id,
                "display_name": identity.display_name,
                "permission": permission.permission,
                "revoked": permission.revoked_at is not None or identity.revoked_at is not None,
                "authenticated_at": permission.authenticated_at.timestamp() if permission.authenticated_at else None,
            }
            for permission, identity in rows
        ]

    async def _permission_by_invite(self, project_id: str, token_hash: str) -> ProjectCollaborationPermission | None:
        query = (
            select(ProjectCollaborationPermission)
            .where(ProjectCollaborationPermission.project_id == project_id)
            .where(ProjectCollaborationPermission.invite_token_hash == token_hash)
        )
        return (await self.session.exec(query)).first()


def _normalize_permission(permission: str) -> str:
    normalized = str(permission).strip().lower()
    if normalized not in COLLABORATION_PERMISSIONS:
        raise CollaborationPermissionError("permission must be exactly one of read, comment, edit")
    return normalized


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

