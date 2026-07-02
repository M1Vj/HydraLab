from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.contracts import RunStatus
from hydra.database.models import AgentRun, IngestionJob, Source
from hydra.updater.activity import (
    DEFAULT_GIT_OPERATION_TRACKER,
    DEFAULT_WRITE_OPERATION_TRACKER,
    GitOperationTracker,
    WriteOperationTracker,
)

ACTIVE_AGENT_RUN_STATUSES = (RunStatus.QUEUED.value, RunStatus.RUNNING.value)
ACTIVE_CONVERSION_STATUSES = ("queued", "running")


@dataclass(frozen=True)
class ActiveWorkStatus:
    active: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def includes(self, reason: str) -> bool:
        return reason in self.reasons


class ActiveWorkGuard:
    def __init__(
        self,
        *,
        git_tracker: GitOperationTracker | None = None,
        write_tracker: WriteOperationTracker | None = None,
    ) -> None:
        self.git_tracker = git_tracker or DEFAULT_GIT_OPERATION_TRACKER
        self.write_tracker = write_tracker or DEFAULT_WRITE_OPERATION_TRACKER

    async def check(self, session: AsyncSession, project_id: str | None = "default") -> ActiveWorkStatus:
        reasons: list[str] = []
        if await self._has_agent_run(session, project_id):
            reasons.append("agent_run")
        if await self._has_conversion(session, project_id):
            reasons.append("conversion")
        if self.git_tracker.active:
            reasons.append("git_operation")
        if self.write_tracker.active:
            reasons.append("write_operation")
        return ActiveWorkStatus(active=bool(reasons), reasons=tuple(reasons))

    async def _has_agent_run(self, session: AsyncSession, project_id: str | None) -> bool:
        stmt = select(AgentRun).where(AgentRun.status.in_(ACTIVE_AGENT_RUN_STATUSES))
        if project_id:
            stmt = stmt.where(AgentRun.project_id == project_id)
        return (await session.exec(stmt)).first() is not None

    async def _has_conversion(self, session: AsyncSession, project_id: str | None) -> bool:
        stmt = select(IngestionJob).where(IngestionJob.status.in_(ACTIVE_CONVERSION_STATUSES))
        if project_id:
            stmt = stmt.join(Source, IngestionJob.source_id == Source.id).where(Source.project_id == project_id)
        return (await session.exec(stmt)).first() is not None
