"""Recoverable Git-backed checkpoints for governed writes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import AgentCheckpoint
from hydra.services.git.service import GitService

class CheckpointService:
    def __init__(self, session: AsyncSession, project_root: Path | None = None, git: GitService | None = None) -> None:
        self.session = session
        self.project_root = project_root or Path.cwd()
        self.git = git or GitService(self.project_root)

    async def create(
        self,
        *,
        project_id: str,
        run_id: str | None,
        label: str,
        target: str = "",
    ) -> AgentCheckpoint:
        git_result: dict[str, Any] | None = self.git.checkpoint(label=label)
        commit = None
        git_ref = None
        if git_result:
            commit = str(git_result.get("commit") or git_result.get("hash") or "")
            git_ref = str(git_result.get("branch") or "HEAD")
        row = AgentCheckpoint(
            project_id=project_id,
            run_id=run_id,
            git_ref=git_ref,
            commit=commit,
            label=label,
            target=target,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    def restore(self, path: str, *, ref: str = "HEAD") -> dict[str, object]:
        return self.git.restore_previous_version(path, ref=ref, auto_checkpoint=False)
