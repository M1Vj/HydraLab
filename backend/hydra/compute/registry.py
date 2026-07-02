"""Compute-backend registry (HL-SAFE-10).

Seeds a default enabled ``local_sandbox`` backend on first read and resolves a
backend by id with an enabled/selectable check. A disabled or unregistered
backend is rejected before a run can be configured, so it can never become a
run target.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.compute.models import CLOUD, DEFAULT_LOCAL_LIMITS, LOCAL_SANDBOX, ComputeBackend


class BackendNotSelectableError(RuntimeError):
    """Raised when a run targets an unknown or disabled backend."""


@dataclass
class ResolvedBackend:
    backend: ComputeBackend
    limits: dict[str, int]

    @property
    def kind(self) -> str:
        return self.backend.kind

    @property
    def is_cloud(self) -> bool:
        return self.backend.kind == CLOUD


class ComputeRegistry:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_seeded(self) -> ComputeBackend:
        existing = await self.session.exec(
            select(ComputeBackend).where(ComputeBackend.kind == LOCAL_SANDBOX)
        )
        seeded = existing.first()
        if seeded is not None:
            return seeded
        backend = ComputeBackend(
            kind=LOCAL_SANDBOX,
            display_name="Local Sandbox",
            enabled=True,
            capabilities_json=json.dumps({"network": False, "gpu": False, "provider_send": False}),
            default_limits_json=json.dumps(DEFAULT_LOCAL_LIMITS.as_dict()),
        )
        self.session.add(backend)
        await self.session.commit()
        await self.session.refresh(backend)
        return backend

    async def list_backends(self, *, include_disabled: bool = True) -> list[ComputeBackend]:
        await self.ensure_seeded()
        query = select(ComputeBackend)
        if not include_disabled:
            query = query.where(ComputeBackend.enabled == True)  # noqa: E712
        res = await self.session.exec(query.order_by(ComputeBackend.created_at.asc()))
        return list(res.all())

    async def register(
        self,
        *,
        kind: str,
        display_name: str,
        enabled: bool = True,
        capabilities: Optional[dict] = None,
        limits: Optional[dict] = None,
    ) -> ComputeBackend:
        backend = ComputeBackend(
            kind=kind,
            display_name=display_name,
            enabled=enabled,
            capabilities_json=json.dumps(capabilities or {}),
            default_limits_json=json.dumps(limits or DEFAULT_LOCAL_LIMITS.as_dict()),
        )
        self.session.add(backend)
        await self.session.commit()
        await self.session.refresh(backend)
        return backend

    async def resolve(self, backend_id: str) -> ResolvedBackend:
        """Resolve a selectable backend or raise. Disabled/unknown -> rejected."""
        await self.ensure_seeded()
        backend = await self.session.get(ComputeBackend, backend_id)
        if backend is None:
            raise BackendNotSelectableError(f"backend '{backend_id}' is not registered")
        if not backend.enabled:
            raise BackendNotSelectableError(f"backend '{backend.display_name or backend_id}' is disabled")
        limits = json.loads(backend.default_limits_json or "{}")
        return ResolvedBackend(backend=backend, limits=limits)
