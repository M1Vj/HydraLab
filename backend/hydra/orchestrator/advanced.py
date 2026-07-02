"""Phase-3 advanced Autopilot configuration.

Advanced settings tune the unified orchestrator only; they do not define a new
mode and cannot relax the Phase-3 autonomy safety shell.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.policy import TRUST_UNTRUSTED
from hydra.autonomy.gate import ActionGate, GateResult, GovernedAction
from hydra.database.models import AgentRunCandidate
from hydra.database.repository import Repository
from hydra.orchestrator.run import RunConfig
from hydra.orchestrator.stages import StageEnum

RankingMethod = Literal["pairwise", "tournament", "elo", "rubric"]
EvolutionMethod = Literal["none", "refine", "merge", "mutate", "crossover"]
ValidationRule = Literal["typecheck", "lint", "test", "build"]
StopCondition = Literal[
    "max_loop_iterations",
    "token_budget",
    "wall_clock_budget",
    "cost_budget",
    "quality_plateau",
    "user_stop",
]

RANKING_METHODS = ("pairwise", "tournament", "elo", "rubric")
EVOLUTION_METHODS = ("none", "refine", "merge", "mutate", "crossover")
VALIDATION_RULES = ("typecheck", "lint", "test", "build")
STOP_CONDITIONS = (
    "max_loop_iterations",
    "token_budget",
    "wall_clock_budget",
    "cost_budget",
    "quality_plateau",
    "user_stop",
)


@dataclass(frozen=True)
class AdvancedConfigValidationError(ValueError):
    field: str
    allowed: str
    received: object

    def __str__(self) -> str:
        return f"{self.field} must be {self.allowed}; received {self.received!r}"


class BudgetPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tokens: int = Field(default=60_000, ge=1, le=200_000)
    wall_clock_seconds: int = Field(default=120, ge=1, le=3_600)
    cost_usd: float | None = Field(default=None, ge=0, le=1_000)


class AdvancedRunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_count: int = Field(default=3, ge=1, le=20)
    population_size: int = Field(default=12, ge=1, le=100)
    compare_enabled: bool = True
    ranking_method: RankingMethod = "pairwise"
    review_depth: int = Field(default=2, ge=1, le=5)
    evolution_method: EvolutionMethod = "refine"
    validation_rules: list[ValidationRule] = Field(default_factory=lambda: ["typecheck", "lint", "test", "build"])
    max_loop_iterations: int = Field(default=1, ge=1, le=100)
    stop_conditions: list[StopCondition] = Field(default_factory=lambda: ["max_loop_iterations", "token_budget", "wall_clock_budget"])
    budget_policy: BudgetPolicy = Field(default_factory=BudgetPolicy)
    checkpoint_frequency: int = Field(default=1, ge=1, le=25)

    @field_validator("validation_rules")
    @classmethod
    def _validation_rules_present(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("validation_rules must include at least one allowed verification command")
        return value

    @field_validator("stop_conditions")
    @classmethod
    def _stop_conditions_present(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("stop_conditions must include at least one condition")
        return value

    def to_run_config(self) -> RunConfig:
        stages = {stage.value: True for stage in StageEnum}
        stages[StageEnum.COMPARE.value] = self.compare_enabled
        return RunConfig.resolve(
            stage_overrides=stages,
            scoring_method=self.ranking_method,
            advanced_config=self.model_dump(),
            block_on_loop_ceiling=True,
        )

    async def governed_action(
        self,
        session: AsyncSession,
        *,
        mode: str,
        action_kind: str,
        target_ref: str,
        full_access_enabled: bool,
        project_id: str = "default",
    ) -> GateResult:
        return await ActionGate(session).govern(
            GovernedAction(
                mode=mode,
                action_kind=action_kind,
                target_kind="setting",
                target_ref=target_ref,
                full_access_enabled=full_access_enabled,
                project_id=project_id,
                summary=f"Advanced preset requested {action_kind}",
                payload={"advanced_config": self.model_dump()},
            )
        )


ADVANCED_RUN_PRESETS: dict[str, AdvancedRunConfig] = {
    "fast": AdvancedRunConfig(
        candidate_count=2,
        population_size=4,
        compare_enabled=True,
        ranking_method="pairwise",
        review_depth=1,
        evolution_method="none",
        validation_rules=["typecheck", "test"],
        max_loop_iterations=1,
        stop_conditions=["max_loop_iterations", "token_budget", "wall_clock_budget"],
        budget_policy=BudgetPolicy(tokens=30_000, wall_clock_seconds=60, cost_usd=None),
        checkpoint_frequency=1,
    ),
    "balanced": AdvancedRunConfig(),
    "deep": AdvancedRunConfig(
        candidate_count=6,
        population_size=24,
        compare_enabled=True,
        ranking_method="tournament",
        review_depth=4,
        evolution_method="merge",
        validation_rules=["typecheck", "lint", "test", "build"],
        max_loop_iterations=3,
        stop_conditions=["max_loop_iterations", "token_budget", "wall_clock_budget", "quality_plateau"],
        budget_policy=BudgetPolicy(tokens=60_000, wall_clock_seconds=120, cost_usd=None),
        checkpoint_frequency=1,
    ),
    "exploratory": AdvancedRunConfig(
        candidate_count=8,
        population_size=40,
        compare_enabled=True,
        ranking_method="elo",
        review_depth=3,
        evolution_method="mutate",
        validation_rules=["typecheck", "test"],
        max_loop_iterations=4,
        stop_conditions=["max_loop_iterations", "token_budget", "wall_clock_budget", "quality_plateau"],
        budget_policy=BudgetPolicy(tokens=80_000, wall_clock_seconds=180, cost_usd=None),
        checkpoint_frequency=2,
    ),
    "strict_evidence": AdvancedRunConfig(
        candidate_count=4,
        population_size=16,
        compare_enabled=True,
        ranking_method="rubric",
        review_depth=5,
        evolution_method="refine",
        validation_rules=["typecheck", "lint", "test", "build"],
        max_loop_iterations=2,
        stop_conditions=["max_loop_iterations", "token_budget", "wall_clock_budget"],
        budget_policy=BudgetPolicy(tokens=60_000, wall_clock_seconds=120, cost_usd=None),
        checkpoint_frequency=1,
    ),
}


def build_advanced_run_config(
    *,
    preset_id: str = "balanced",
    overrides: dict[str, Any] | None = None,
) -> AdvancedRunConfig:
    base = ADVANCED_RUN_PRESETS.get(preset_id)
    if base is None:
        raise AdvancedConfigValidationError("preset_id", ", ".join(sorted(ADVANCED_RUN_PRESETS)), preset_id)
    payload = base.model_dump()
    payload.update(overrides or {})
    try:
        return AdvancedRunConfig.model_validate(payload)
    except ValidationError as exc:
        raise _validation_error(exc) from exc


class CandidateStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def store_ranked_candidates(
        self,
        *,
        run_id: str,
        project_id: str | None,
        ranking_method: str,
        candidates: list[dict[str, Any]],
    ) -> list[AgentRunCandidate]:
        rows: list[AgentRunCandidate] = []
        for index, candidate in enumerate(candidates):
            candidate_id = str(candidate.get("id") or f"candidate-{index + 1}")
            score = float(candidate.get("score") or candidate.get("ranking_score") or 0)
            row = AgentRunCandidate(
                run_id=run_id,
                project_id=project_id,
                candidate_id=candidate_id,
                candidate_artifact_json=json.dumps(candidate, sort_keys=True),
                ranking_score=score,
                ranking_method=ranking_method,
            )
            self.session.add(row)
            rows.append(row)
        await self.session.commit()
        for row in rows:
            await self.session.refresh(row)
        return rows

    async def list_for_run(self, run_id: str) -> list[AgentRunCandidate]:
        res = await self.session.exec(
            select(AgentRunCandidate).where(AgentRunCandidate.run_id == run_id).order_by(AgentRunCandidate.created_at.asc())
        )
        return list(res.all())


async def route_untrusted_advanced_preset(
    session: AsyncSession,
    *,
    project_id: str,
    config: AdvancedRunConfig,
    provenance: str,
    origin_id: str | None = None,
) -> dict[str, Any]:
    if provenance != TRUST_UNTRUSTED:
        return {"status": "trusted", "review_item_id": None}
    return await Repository(session).create_review_item(
        {
            "project_id": project_id,
            "item_type": "advanced-run-config-preset",
            "title": "Review imported advanced run preset",
            "summary": "Untrusted-provenance preset is data, not instructions; approve before use.",
            "origin_type": "advanced_preset_import",
            "origin_id": origin_id,
            "target_type": "autopilot_run_config",
            "target_id": project_id,
            "payload": {
                "trust_origin": provenance,
                "advanced_config": config.model_dump(),
            },
        }
    )


def advanced_validation_error_response(error: AdvancedConfigValidationError) -> dict[str, object]:
    return {"field": error.field, "allowed": error.allowed, "received": error.received, "message": str(error)}


def _validation_error(exc: ValidationError) -> AdvancedConfigValidationError:
    error = exc.errors()[0]
    loc = error.get("loc") or ("advanced_config",)
    field = ".".join(str(part) for part in loc)
    if field.startswith("validation_rules."):
        field = "validation_rules"
    if field.startswith("stop_conditions."):
        field = "stop_conditions"
    received = error.get("input")
    return AdvancedConfigValidationError(field=field, allowed=_allowed_for_field(field), received=received)


def _allowed_for_field(field: str) -> str:
    if field == "candidate_count":
        return "1..20"
    if field == "population_size":
        return "1..100"
    if field == "ranking_method":
        return ", ".join(sorted(RANKING_METHODS))
    if field == "review_depth":
        return "1..5"
    if field == "evolution_method":
        return ", ".join(sorted(EVOLUTION_METHODS))
    if field == "validation_rules":
        return ", ".join(sorted(VALIDATION_RULES))
    if field == "max_loop_iterations":
        return "1..100"
    if field == "stop_conditions":
        return ", ".join(sorted(STOP_CONDITIONS))
    if field == "budget_policy.tokens":
        return "1..200000"
    if field == "budget_policy.wall_clock_seconds":
        return "1..3600"
    if field == "budget_policy.cost_usd":
        return "0..1000"
    if field == "checkpoint_frequency":
        return "1..25"
    return "one of the documented AdvancedRunConfig fields"
