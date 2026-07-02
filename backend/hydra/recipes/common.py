from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.contracts import RunStatus, Trace
from hydra.agents.runs import RunBudget, RunRepository
from hydra.database.models import AgentRun, ReviewItem
from hydra.orchestrator.dispatch import DispatchAction, DispatchGuard, PrivacyPosture
from hydra.orchestrator.run import RunConfig, RunExecutionResult, RunStateMachine
from hydra.orchestrator.stages import Stage, StageEnum

RECIPE_INPUT_SCHEMA = {
    "type": "object",
    "required": ["draft_or_source", "target_venue_style", "source_scope"],
    "properties": {
        "draft_or_source": {"type": "object"},
        "target_venue_style": {"type": "string"},
        "source_scope": {"type": "array", "items": {"type": "string"}},
    },
}

DEFAULT_PRESETS = {
    "fast": {"candidate_count": 2, "review_depth": "light"},
    "balanced": {"candidate_count": 4, "review_depth": "standard"},
    "deep": {"candidate_count": 6, "review_depth": "deeper"},
    "exploratory": {"candidate_count": 6, "review_depth": "broad"},
    "strict_evidence": {"candidate_count": 3, "review_depth": "strict"},
}


@dataclass
class RecipeRunResult:
    run_id: str
    state: str
    trace: Trace
    artifacts: list[dict[str, Any]]
    review_item_id: str | None = None
    review_item: ReviewItem | None = None


def recipe_config(
    *,
    recipe_id: str,
    name: str,
    stages: list[StageEnum],
    output_artifact_type: str,
) -> dict[str, Any]:
    # RECONCILE: shares recipe-config shape with 02-04.
    return {
        "id": recipe_id,
        "name": name,
        "input_schema": RECIPE_INPUT_SCHEMA,
        "stages": [stage.value for stage in stages],
        "defaults": DEFAULT_PRESETS,
        "approval_gates": ["inline_accept_reject"],
        "output_artifact_type": output_artifact_type,
        "bounded_pass": True,
    }


async def run_recipe_machine(
    session: AsyncSession,
    *,
    recipe_id: str,
    stages: list[StageEnum],
    stage_impls: dict[StageEnum, Stage],
    inputs: dict[str, Any],
    project_id: str = "default",
    mode: str = "passive",
    budget: RunBudget | None = None,
    privacy: dict[str, Any] | None = None,
) -> RecipeRunResult:
    blocked = await _maybe_block_offline(session, recipe_id=recipe_id, inputs=inputs, project_id=project_id, mode=mode, privacy=privacy)
    if blocked is not None:
        return blocked

    config = RunConfig.resolve(stage_overrides={stage.value: True for stage in stages})
    execution = await RunStateMachine(
        RunRepository(session),
        config,
        stages=stage_impls,
        budget=budget,
    ).start(
        project_id=project_id,
        mode=mode,
        recipe=recipe_id,
        inputs=[inputs],
        data={"recipe_inputs": inputs},
    )
    return await recipe_result(session, execution)


async def recipe_result(session: AsyncSession, execution: RunExecutionResult) -> RecipeRunResult:
    run = await session.get(AgentRun, execution.run_id)
    trace = await RunRepository(session).get_trace(execution.run_id)
    return RecipeRunResult(
        run_id=execution.run_id,
        state=execution.state,
        trace=trace,
        artifacts=json.loads((run.artifacts if run else "[]") or "[]"),
    )


async def _maybe_block_offline(
    session: AsyncSession,
    *,
    recipe_id: str,
    inputs: dict[str, Any],
    project_id: str,
    mode: str,
    privacy: dict[str, Any] | None,
) -> RecipeRunResult | None:
    posture = PrivacyPosture(
        g3_enabled=bool((privacy or {}).get("g3_enabled", True)),
        offline_only=bool((privacy or {}).get("offline_only", False)),
        opt_ins=dict((privacy or {}).get("opt_ins") or {}),
        egress_items=[
            {
                "type": "selection",
                "id_or_path": "recipe:draft_or_source",
                "label": str((inputs.get("draft_or_source") or {}).get("title") or recipe_id),
            }
        ],
    )
    result = await DispatchGuard(session).dispatch(
        DispatchAction(
            mode=mode,
            action_kind="provider_send",
            target_kind="provider",
            target_ref=recipe_id,
            project_id=project_id,
            privacy=posture,
            summary=f"Run {recipe_id}",
        )
    )
    if result.status != "permission-denied":
        return None

    runs = RunRepository(session)
    run = await runs.create_run(project_id=project_id, mode=mode, recipe=recipe_id, inputs=[inputs])
    await runs.append_step(
        run.id,
        kind="consent.blocked",
        status=RunStatus.BLOCKED.value,
        summary=result.reason or "offline-only mode blocks provider sends",
        payload={"state": "permission-denied", "reason": result.reason},
    )
    await runs.complete_run(run.id, status=RunStatus.BLOCKED.value)
    trace = await runs.get_trace(run.id)
    return RecipeRunResult(run_id=run.id, state="permission-denied", trace=trace, artifacts=[])
