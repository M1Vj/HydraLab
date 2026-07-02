"""Bounded Phase-2 run state machine with incremental trace persistence."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from hydra.agents.contracts import RunStatus, StepStatus
from hydra.agents.runs import RunBudget, RunRepository, budget_exceeded
from hydra.database.models import AgentRun
from hydra.orchestrator.stages import (
    CANONICAL_STAGE_ORDER,
    Stage,
    StageContext,
    StageEnum,
    StageResult,
    default_stages,
)


class OrchestratorConfigError(ValueError):
    """Invalid bounded Phase-2 run configuration."""


@dataclass(frozen=True)
class RunConfig:
    enabled_stages: dict[StageEnum, bool]
    scoring_method: str = "rubric"
    stage_toggles: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def resolve(
        cls,
        *,
        global_enabled: dict[str, bool] | None = None,
        stage_overrides: dict[str, bool] | None = None,
        scoring_method: str = "rubric",
        loop_count: int = 1,
        stage_toggles: dict[str, dict[str, Any]] | None = None,
    ) -> "RunConfig":
        if loop_count > 1:
            raise OrchestratorConfigError("loop_count > 1 is Phase-3 Autopilot scope and is rejected")
        enabled: dict[StageEnum, bool] = {stage: False for stage in CANONICAL_STAGE_ORDER}
        for source in (global_enabled or {}, stage_overrides or {}):
            for stage_id, value in source.items():
                stage = _stage_from_id(stage_id)
                enabled[stage] = bool(value)
        toggles = stage_toggles or {}
        for stage_id in toggles:
            _stage_from_id(stage_id)
        return cls(
            enabled_stages=enabled,
            scoring_method=scoring_method,
            stage_toggles=dict(toggles),
        )

    @classmethod
    def all_enabled(cls, *, scoring_method: str = "rubric") -> "RunConfig":
        return cls.resolve(
            global_enabled={stage.value: True for stage in CANONICAL_STAGE_ORDER},
            scoring_method=scoring_method,
        )


@dataclass
class RunExecutionResult:
    run_id: str
    state: str
    completed_stages: list[StageEnum] = field(default_factory=list)


class RunStateMachine:
    def __init__(
        self,
        repository: RunRepository,
        config: RunConfig,
        *,
        stages: dict[StageEnum, Stage] | None = None,
        budget: RunBudget | None = None,
    ) -> None:
        self.repository = repository
        self.config = config
        self.stages = {**default_stages(config.scoring_method), **(stages or {})}
        self.budget = budget or RunBudget()
        self.run_id = ""

    async def start(
        self,
        *,
        project_id: str,
        mode: str,
        recipe: str = "bounded-stage-pass",
        inputs: list[Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> RunExecutionResult:
        run = await self.repository.create_run(project_id=project_id, mode=mode, recipe=recipe, inputs=inputs)
        self.run_id = run.id
        return await self.resume(run_id=run.id, project_id=project_id, mode=mode, data=data)

    async def resume(
        self,
        *,
        run_id: str,
        project_id: str,
        mode: str,
        data: dict[str, Any] | None = None,
    ) -> RunExecutionResult:
        self.run_id = run_id
        started = time.monotonic()
        data = dict(data or {})
        completed: list[StageEnum] = []

        for stage in CANONICAL_STAGE_ORDER:
            if not self.config.enabled_stages.get(stage, False):
                await self.repository.append_step(
                    run_id,
                    kind=f"stage.{stage.value}",
                    status="skipped",
                    summary=f"{stage.value} disabled for this bounded run",
                    payload={"stage": stage.value, "enabled": False},
                )
                continue

            stage_impl = self.stages[stage]
            ctx = StageContext(run_id=run_id, project_id=project_id, mode=mode, data=data, config=self.config)
            try:
                result = await stage_impl.run(ctx)
            except Exception as exc:
                await self.repository.append_step(
                    run_id,
                    kind=f"stage.{stage.value}",
                    status=StepStatus.FAILED.value,
                    summary=str(exc),
                    payload={"stage": stage.value, "state": "failed"},
                )
                await self.repository.complete_run(run_id, status=RunStatus.FAILED.value)
                return RunExecutionResult(run_id=run_id, state="failed", completed_stages=completed)

            await self._persist_result(run_id, result)
            completed.append(stage)

            if result.stop_state == "awaiting_approval":
                await self.repository.complete_run(run_id, status=RunStatus.BLOCKED.value)
                return RunExecutionResult(run_id=run_id, state="awaiting_approval", completed_stages=completed)

            if await self._budget_blocked(run_id, started):
                return RunExecutionResult(run_id=run_id, state="budget_blocked", completed_stages=completed)

        await self.repository.complete_run(run_id, status=RunStatus.COMPLETED.value)
        return RunExecutionResult(run_id=run_id, state="completed", completed_stages=completed)

    async def _persist_result(self, run_id: str, result: StageResult) -> None:
        await self.repository.append_step(
            run_id,
            kind=f"stage.{result.stage.value}",
            status=result.status,
            summary=result.summary,
            tokens=result.tokens,
            trust_origin=result.trust_origin,
            payload={"stage": result.stage.value, **result.payload},
        )
        if result.artifacts:
            run = await self.repository.session.get(AgentRun, run_id)
            if run is None:
                return
            current = json.loads(run.artifacts or "[]")
            current.extend(result.artifacts)
            run.artifacts = json.dumps(current, sort_keys=True)
            self.repository.session.add(run)
            await self.repository.session.commit()

    async def _budget_blocked(self, run_id: str, started: float) -> bool:
        trace = await self.repository.get_trace(run_id)
        if not budget_exceeded(
            tokens_used=trace.tokens,
            elapsed_seconds=time.monotonic() - started,
            budget=self.budget,
        ):
            return False
        await self.repository.append_step(
            run_id,
            kind="budget.blocked",
            status=RunStatus.BLOCKED.value,
            summary="budget ceiling reached; choose continue, raise the ceiling, or stop",
            payload={"state": "budget_blocked"},
        )
        await self.repository.block_on_budget(run_id)
        return True


def _stage_from_id(stage_id: str | StageEnum) -> StageEnum:
    if isinstance(stage_id, StageEnum):
        return stage_id
    try:
        return StageEnum(str(stage_id))
    except ValueError as exc:
        raise OrchestratorConfigError(f"undefined stage id: {stage_id}") from exc
