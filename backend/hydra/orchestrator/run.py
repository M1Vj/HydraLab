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
    scoring_method: str = "pairwise"
    stage_toggles: dict[str, dict[str, Any]] = field(default_factory=dict)
    advanced_config: dict[str, Any] = field(default_factory=dict)
    block_on_loop_ceiling: bool = False

    @classmethod
    def resolve(
        cls,
        *,
        global_enabled: dict[str, bool] | None = None,
        stage_overrides: dict[str, bool] | None = None,
        scoring_method: str = "pairwise",
        loop_count: int = 1,
        stage_toggles: dict[str, dict[str, Any]] | None = None,
        advanced_config: dict[str, Any] | None = None,
        block_on_loop_ceiling: bool = False,
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
            advanced_config=dict(advanced_config or {}),
            block_on_loop_ceiling=block_on_loop_ceiling,
        )

    @classmethod
    def all_enabled(cls, *, scoring_method: str = "pairwise") -> "RunConfig":
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
        cancel_after_stage: StageEnum | None = None,
        action_gate: Any = None,
        full_access_enabled: bool = False,
    ) -> None:
        self.repository = repository
        self.config = config
        self.stages = {**default_stages(config.scoring_method), **(stages or {})}
        self.budget = budget or RunBudget()
        self.cancel_after_stage = cancel_after_stage
        self.action_gate = action_gate
        self.full_access_enabled = full_access_enabled
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
            ctx = StageContext(
                run_id=run_id,
                project_id=project_id,
                mode=mode,
                data=data,
                config=self.config,
                full_access_enabled=self.full_access_enabled,
                action_gate=self.action_gate,
            )
            try:
                result = await stage_impl.run(ctx)
                await self._govern_actions(run_id, project_id, mode, result)
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

            await self._persist_result(run_id, project_id, result)
            completed.append(stage)

            if self.cancel_after_stage == stage:
                await self.repository.cancel_run(run_id)
                return RunExecutionResult(run_id=run_id, state="cancelled", completed_stages=completed)

            if result.stop_state == "awaiting_approval":
                await self.repository.complete_run(run_id, status=RunStatus.BLOCKED.value)
                return RunExecutionResult(run_id=run_id, state="awaiting_approval", completed_stages=completed)

            if await self._budget_blocked(run_id, started):
                return RunExecutionResult(run_id=run_id, state="budget_blocked", completed_stages=completed)

        await self.repository.complete_run(run_id, status=RunStatus.COMPLETED.value)
        return RunExecutionResult(run_id=run_id, state="completed", completed_stages=completed)

    async def _govern_actions(self, run_id: str, project_id: str, mode: str, result: StageResult) -> None:
        """Route every stage-proposed substantive action through the ActionGate.

        The run's mode/project/run id are authoritative and stamped onto each
        proposed action so a stage can never widen the active mode's scope
        (HL-MODE-30). With no gate wired (plain Phase-2 run) this is a no-op.
        """
        if self.action_gate is None or not result.proposed_actions:
            return
        for action in result.proposed_actions:
            action.mode = mode
            action.project_id = project_id
            action.run_id = run_id
            # Authoritative: the run's full-access flag is the ONLY source. A stage
            # must never keep a self-set full_access_enabled=True — that is the
            # policy input that flips approval -> auto-apply, i.e. scope widening.
            action.full_access_enabled = self.full_access_enabled
            gate_result = await self.action_gate.govern(action, apply_fn=getattr(action, "apply_fn", None))
            result.governed.append(gate_result)

    async def _persist_result(self, run_id: str, project_id: str, result: StageResult) -> None:
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
        if result.stage == StageEnum.COMPARE and result.payload.get("method"):
            await self._persist_compare_audit(run_id, project_id, str(result.payload["method"]))
            await self._persist_ranked_candidates(run_id, project_id, result)

    async def _persist_compare_audit(self, run_id: str, project_id: str, method: str) -> None:
        from hydra.autonomy.audit import AuditLedger

        await AuditLedger(self.repository.session).append(
            project_id=project_id,
            run_id=run_id,
            actor="orchestrator",
            action="compare.ranking_method",
            risk_level="low",
            target=method,
            approval_state="recorded",
        )

    async def _persist_ranked_candidates(self, run_id: str, project_id: str, result: StageResult) -> None:
        from hydra.orchestrator.advanced import CandidateStore

        ranking: list[dict[str, Any]] = []
        for artifact in result.artifacts:
            if artifact.get("kind") == "ranking":
                ranking = list(artifact.get("ranking") or [])
                break
        if not ranking:
            return
        await CandidateStore(self.repository.session).store_ranked_candidates(
            run_id=run_id,
            project_id=project_id,
            ranking_method=str(result.payload["method"]),
            candidates=ranking,
        )

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
