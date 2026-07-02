"""Closed-loop Autopilot wrapper around the bounded run state machine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.contracts import RunStatus
from hydra.agents.runs import RunBudget, RunRepository, budget_exceeded
from hydra.autonomy.policy import AutonomyPolicy, AutonomyPolicyError
from hydra.database.models import AgentRun
from hydra.orchestrator.run import RunConfig, RunExecutionResult, RunStateMachine

RunnerFactory = Callable[[RunRepository, RunConfig, RunBudget], RunStateMachine]

@dataclass
class AutopilotLoop:
    session: AsyncSession
    policy: AutonomyPolicy
    config: RunConfig
    runner_factory: RunnerFactory | None = None
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
        started = time.monotonic()
        last: RunExecutionResult | None = None

        while self.loop_count < self.policy.max_loop_count:
            if self.cancelled:
                break
            if budget_exceeded(tokens_used=0, elapsed_seconds=time.monotonic() - started, budget=budget):
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
        return RunStateMachine(repo, self.config, budget=budget)
