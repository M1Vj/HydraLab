"""Closed-loop Autopilot wrapper around the bounded run state machine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.contracts import RunStatus
from hydra.agents.runs import RunBudget, RunRepository, budget_exceeded
from hydra.autonomy.gate import ActionGate
from hydra.autonomy.policy import AutonomyPolicy, AutonomyPolicyError
from hydra.database.models import AgentRun
from hydra.orchestrator.run import RunConfig, RunExecutionResult, RunStateMachine

RunnerFactory = Callable[[RunRepository, RunConfig, RunBudget], RunStateMachine]


def _elapsed_seconds(run: AgentRun | None, fallback_monotonic: float) -> float:
    """Wall-clock elapsed for the budget gate.

    Measured against the run's persisted ``started_at`` so pausing and resuming
    cannot reset the clock — a resumed run keeps accumulating against its
    original start instead of restarting from zero each ``_run`` call. Falls
    back to a process-local monotonic clock only before the run row exists.
    SQLite may hand back a naive datetime, so an absent tzinfo is treated as UTC.
    """
    if run is not None and run.started_at is not None:
        started_at = run.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())
    return time.monotonic() - fallback_monotonic

@dataclass
class AutopilotLoop:
    session: AsyncSession
    policy: AutonomyPolicy
    config: RunConfig
    runner_factory: RunnerFactory | None = None
    full_access_enabled: bool = False
    loop_count: int = 0
    stop_conditions: list[str] = field(default_factory=list)
    cancelled: bool = False
    stop_reason: str = ""

    def __post_init__(self) -> None:
        if self.policy is None:
            raise AutonomyPolicyError("missing run-governance policy; unresolved fields: mode, budget limits, max loop count, stop conditions")
        if not self.policy.autopilot_enabled:
            raise AutonomyPolicyError("Autopilot is disabled for this project")
        self.stop_conditions = list(self.policy.stop_conditions)

    async def start(self, *, project_id: str, inputs: list[Any] | None = None) -> RunExecutionResult:
        return await self._run(project_id=project_id, inputs=inputs, run_id=None)

    async def resume(self, *, run_id: str, project_id: str) -> RunExecutionResult:
        repo = RunRepository(self.session)
        run = await repo.pause_run(run_id, False)
        if run is None:
            raise ValueError("run not found")
        return await self._run(project_id=project_id, inputs=None, run_id=run_id)

    async def pause(self, run_id: str) -> None:
        await RunRepository(self.session).pause_run(run_id, True)

    async def cancel(self, run_id: str, *, stop_reason: str = "cancelled by user") -> None:
        self.cancelled = True
        self.stop_reason = stop_reason
        await RunRepository(self.session).cancel_run(run_id, stop_reason=stop_reason)

    async def retry(self, *, project_id: str, inputs: list[Any] | None = None) -> RunExecutionResult:
        self.loop_count = 0
        self.cancelled = False
        self.stop_reason = ""
        return await self.start(project_id=project_id, inputs=inputs)

    async def _run(self, *, project_id: str, inputs: list[Any] | None, run_id: str | None) -> RunExecutionResult:
        repo = RunRepository(self.session)
        budget = RunBudget(
            run_budget_tokens=self.policy.budget_limits.tokens,
            wall_clock_seconds=self.policy.budget_limits.wall_clock_seconds,
        )
        # Fallback clock used only until the run row (with started_at) exists.
        started = time.monotonic()
        last: RunExecutionResult | None = None

        while self.loop_count < self.policy.max_loop_count:
            # Re-read persisted state each iteration so an out-of-band cancel
            # (a separate request flipping the run row) actually stops the loop
            # before the next iteration (M2), and the token ceiling is enforced
            # against the run's real consumption, not a hardcoded zero (M1).
            # populate_existing forces a fresh read past the identity map so an
            # out-of-band cancel committed by ANOTHER session (the cancel request
            # runs on its own session) is actually observed here (M2). Without it,
            # expire_on_commit=False returns the stale in-loop row.
            current = (
                await self.session.get(AgentRun, run_id, populate_existing=True) if run_id else None
            )
            if self.cancelled or (current is not None and current.status == RunStatus.CANCELLED.value):
                self.stop_reason = self.stop_reason or "cancelled by user"
                break
            tokens_used = current.tokens_used if current is not None else 0
            if budget_exceeded(tokens_used=tokens_used, elapsed_seconds=_elapsed_seconds(current, started), budget=budget):
                self.stop_reason = "budget exceeded"
                if run_id:
                    await repo.block_on_budget(run_id)
                break
            runner = self._runner(repo, budget)
            if run_id and self.loop_count == 0:
                last = await runner.resume(run_id=run_id, project_id=project_id, mode=self.policy.mode)
            else:
                last = await runner.start(
                    project_id=project_id,
                    mode=self.policy.mode,
                    recipe="autopilot-loop",
                    inputs=inputs,
                    data={"autopilot": True, "loop_index": self.loop_count},
                )
                run_id = last.run_id
            self.loop_count += 1
            if last.state not in {"completed"}:
                self.stop_reason = last.state
                break

        if run_id and self.loop_count >= self.policy.max_loop_count:
            self.stop_reason = "max_loop_count"
            if self.config.block_on_loop_ceiling:
                self.stop_reason = "max_loop_iterations"
                await repo.append_step(
                    run_id,
                    kind="loop_control.blocked",
                    status=RunStatus.BLOCKED.value,
                    summary="max loop iterations reached; choose continue, raise the ceiling, or stop",
                    payload={"state": "loop_blocked", "ceiling": "max_loop_iterations"},
                )
                run = await repo.block_on_budget(run_id)
            else:
                run = await self.session.get(AgentRun, run_id)
                if run is not None and run.status == RunStatus.RUNNING.value:
                    await repo.complete_run(run_id, status=RunStatus.COMPLETED.value)
            if run is not None:
                run.stop_reason = self.stop_reason
                self.session.add(run)
                await self.session.commit()
        return last or RunExecutionResult(run_id=run_id or "", state=self.stop_reason or "stopped")

    def _runner(self, repo: RunRepository, budget: RunBudget) -> RunStateMachine:
        if self.runner_factory is not None:
            return self.runner_factory(repo, self.config, budget)
        return RunStateMachine(
            repo,
            self.config,
            budget=budget,
            action_gate=ActionGate(self.session),
            full_access_enabled=self.full_access_enabled,
        )
