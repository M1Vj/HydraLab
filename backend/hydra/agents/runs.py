"""Run/trace repository: incremental persistence, cancel, budget bounds.

Each run persists its trace one step at a time (HL-ASSIST-04). Cancelling a run
leaves its already-persisted step prefix intact and reports ``status="cancelled"``.
A run blocks-and-prompts at the ``[assistant].run_budget`` ceiling rather than
silently continuing. This module imports no agent framework — it speaks only the
HydraLab contracts in :mod:`hydra.agents.contracts`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.contracts import Artifact, RunStatus, StepStatus, Trace, TraceStep
from hydra.database.models import AgentRun, AgentRunStep

# Default budget ceiling (Section 36.3): 60,000 tokens AND 120 seconds.
DEFAULT_RUN_BUDGET_TOKENS = 60_000
DEFAULT_WALL_CLOCK_SECONDS = 120


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RunBudget:
    run_budget_tokens: int = DEFAULT_RUN_BUDGET_TOKENS
    wall_clock_seconds: int = DEFAULT_WALL_CLOCK_SECONDS


def budget_exceeded(*, tokens_used: int, elapsed_seconds: float, budget: RunBudget) -> bool:
    """True when either the token OR wall-clock ceiling is reached."""

    return tokens_used >= budget.run_budget_tokens or elapsed_seconds >= budget.wall_clock_seconds


class RunRepository:
    """Persists runs and their step-by-step traces incrementally."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(
        self,
        *,
        project_id: str,
        mode: str,
        recipe: Optional[str] = None,
        stage: str = "",
        inputs: Optional[list[Any]] = None,
    ) -> AgentRun:
        run = AgentRun(
            project_id=project_id,
            mode=mode,
            recipe=recipe,
            stage=stage,
            inputs_ref=json.dumps(inputs or [], sort_keys=True),
            status=RunStatus.RUNNING.value,
            started_at=_utcnow(),
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def append_step(
        self,
        run_id: str,
        *,
        kind: str,
        summary: str = "",
        status: str = StepStatus.COMPLETED.value,
        tokens: int = 0,
        trust_origin: str = "user",
        skill_id: Optional[str] = None,
        capability: Optional[str] = None,
        denied_capability: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> AgentRunStep:
        """Persist one step and flush immediately (incremental persistence)."""

        count = await self._step_count(run_id)
        step = AgentRunStep(
            run_id=run_id,
            step_index=count,
            kind=kind,
            summary=summary,
            status=status,
            tokens=tokens,
            trust_origin=trust_origin,
            skill_id=skill_id,
            capability=capability,
            denied_capability=denied_capability,
            payload_json=json.dumps(payload or {}, sort_keys=True),
        )
        self.session.add(step)
        run = await self.session.get(AgentRun, run_id)
        if run is not None:
            run.tokens_used = (run.tokens_used or 0) + int(tokens)
            run.updated_at = _utcnow()
            self.session.add(run)
        await self.session.commit()
        await self.session.refresh(step)
        return step

    async def cancel_run(self, run_id: str) -> Optional[AgentRun]:
        """Cancel a run, leaving its completed step prefix intact."""

        run = await self.session.get(AgentRun, run_id)
        if run is None:
            return None
        run.status = RunStatus.CANCELLED.value
        run.ended_at = _utcnow()
        run.updated_at = _utcnow()
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def pause_run(self, run_id: str, paused: bool = True) -> Optional[AgentRun]:
        run = await self.session.get(AgentRun, run_id)
        if run is None:
            return None
        run.paused = paused
        run.status = RunStatus.PAUSED.value if paused else RunStatus.RUNNING.value
        run.updated_at = _utcnow()
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def complete_run(
        self, run_id: str, *, status: str = RunStatus.COMPLETED.value
    ) -> Optional[AgentRun]:
        run = await self.session.get(AgentRun, run_id)
        if run is None:
            return None
        run.status = status
        run.ended_at = _utcnow()
        run.updated_at = _utcnow()
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def block_on_budget(self, run_id: str) -> Optional[AgentRun]:
        """Block-and-prompt at the budget ceiling instead of continuing."""

        return await self.complete_run(run_id, status=RunStatus.BLOCKED.value)

    async def _step_count(self, run_id: str) -> int:
        res = await self.session.exec(select(AgentRunStep).where(AgentRunStep.run_id == run_id))
        return len(res.all())

    async def list_steps(self, run_id: str) -> list[AgentRunStep]:
        res = await self.session.exec(
            select(AgentRunStep).where(AgentRunStep.run_id == run_id).order_by(AgentRunStep.step_index.asc())
        )
        return list(res.all())

    async def get_trace(self, run_id: str) -> Trace:
        steps = await self.list_steps(run_id)
        trace = Trace(run_id=run_id)
        for step in steps:
            trace.steps.append(
                TraceStep(
                    index=step.step_index,
                    kind=step.kind,
                    status=step.status,
                    summary=step.summary,
                    tokens=step.tokens,
                    trust_origin=step.trust_origin,
                    skill_id=step.skill_id,
                    capability=step.capability,
                    denied_capability=step.denied_capability,
                    payload=json.loads(step.payload_json or "{}"),
                )
            )
        return trace

    async def artifacts_for(self, run_id: str) -> list[Artifact]:
        run = await self.session.get(AgentRun, run_id)
        if run is None:
            return []
        raw = json.loads(run.artifacts or "[]")
        return [
            Artifact(
                id=str(item.get("id", "")),
                kind=str(item.get("kind", "")),
                ref=str(item.get("ref", "")),
                summary=str(item.get("summary", "")),
            )
            for item in raw
        ]
