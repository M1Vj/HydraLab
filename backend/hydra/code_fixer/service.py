"""App-code fixer service (branch 03-05).

A thin specialization of the self-evolution workflow for ``app_code`` diffs. It
reuses :class:`hydra.self_evolution.service.SelfEvolutionService` for the
checkpoint → apply → verify → rollback primitives rather than reimplementing
them, and forces every proposed change into the ``app_code`` category so the
``backend/hydra/code_fixer/`` module has a real, directly-exercisable surface
(``backend/tests/test_code_fixer.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.autonomy.audit import AuditLedger
from hydra.autonomy.checkpoints import CheckpointService
from hydra.database.models import SelfEvolutionChange
from hydra.self_evolution.models import APP_CODE, ProposedChange
from hydra.self_evolution.service import SelfEvolutionError, SelfEvolutionService
from hydra.self_evolution.verification import VerificationRunner


class CodeFixerError(RuntimeError):
    """Raised for a code-fixer specific guard failure."""


class CodeFixerService:
    """Propose/approve/deny app-code fixes over the shared self-evolution engine."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        project_root: Path,
        checkpoints: CheckpointService,
        audit: AuditLedger,
        verifier: VerificationRunner,
    ) -> None:
        self.engine = SelfEvolutionService(
            session,
            project_root=project_root,
            checkpoints=checkpoints,
            audit=audit,
            verifier=verifier,
        )

    async def propose_fix(
        self,
        *,
        project_id: str,
        run_id: str | None,
        changes: Iterable[ProposedChange],
        trigger: str = "user",
    ) -> list[SelfEvolutionChange]:
        """Propose one or more app-code fixes (category forced to ``app_code``)."""
        coerced: list[ProposedChange] = []
        for change in changes:
            change.category = APP_CODE
            coerced.append(change)
        return await self.engine.propose(
            project_id=project_id, run_id=run_id, changes=coerced, trigger=trigger
        )

    async def approve(self, change_id: str, *, actor: str = "user") -> SelfEvolutionChange:
        return await self.engine.approve(change_id, actor=actor)

    async def deny(self, change_id: str, *, actor: str = "user") -> SelfEvolutionChange:
        return await self.engine.deny(change_id, actor=actor)

    async def list_changes(self, *, project_id: str) -> list[SelfEvolutionChange]:
        return await self.engine.list_changes(project_id=project_id)


__all__ = ["CodeFixerError", "CodeFixerService", "SelfEvolutionError"]
