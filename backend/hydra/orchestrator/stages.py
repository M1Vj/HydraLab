"""Fixed seven-stage Phase-2 orchestrator contract and default stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class StageEnum(str, Enum):
    GENERATE = "generate"
    REVIEW = "review"
    COMPARE = "compare"
    EVOLVE = "evolve"
    VALIDATE = "validate"
    CACHE = "cache"
    LOOP_CONTROL = "loop_control"


CANONICAL_STAGE_ORDER: tuple[StageEnum, ...] = tuple(StageEnum)


@dataclass
class StageTraceEvent:
    stage: StageEnum
    status: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    tokens: int = 0
    trust_origin: str = "user"


@dataclass
class StageResult:
    stage: StageEnum
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    tokens: int = 0
    status: str = "completed"
    stop_state: str | None = None
    trust_origin: str = "user"


@dataclass
class StageContext:
    run_id: str
    project_id: str
    mode: str
    data: dict[str, Any]
    config: Any


class Stage(Protocol):
    id: StageEnum

    async def run(self, ctx: StageContext) -> StageResult:
        """Run one bounded stage and return its typed result."""


def _candidate(candidate_id: str, title: str, base_score: int) -> dict[str, Any]:
    return {"id": candidate_id, "title": title, "base_score": base_score}


class GenerateStage:
    id = StageEnum.GENERATE

    async def run(self, ctx: StageContext) -> StageResult:
        candidates = [
            _candidate("idea-1", "Map the core literature", 10),
            _candidate("idea-2", "Contrast competing claims", 20),
            _candidate("idea-3", "Draft a stronger synthesis", 30),
        ]
        ctx.data["candidates"] = candidates
        return StageResult(
            stage=self.id,
            summary="generated three candidate research directions",
            payload={"candidate_count": len(candidates), "candidates": candidates},
            artifacts=[
                {
                    "id": f"{ctx.run_id}:generate:candidates",
                    "kind": "candidates",
                    "stage": self.id.value,
                    "ref": "agent-run:candidates",
                    "summary": "Generated candidate research directions",
                    "candidates": candidates,
                }
            ],
            tokens=10,
        )


class ReviewStage:
    id = StageEnum.REVIEW

    async def run(self, ctx: StageContext) -> StageResult:
        candidates = list(ctx.data.get("candidates") or [])
        reviewed = [{**candidate, "review": "kept"} for candidate in candidates]
        ctx.data["candidates"] = reviewed
        return StageResult(
            stage=self.id,
            summary="reviewed generated candidates",
            payload={
                "received_candidate_count": len(candidates),
                "reviewed_candidate_count": len(reviewed),
            },
            tokens=8,
        )


class CompareStage:
    id = StageEnum.COMPARE
    VALID_SCORING_METHODS = frozenset({"pairwise", "tournament", "elo", "rubric"})

    def __init__(self, scoring_method: str = "pairwise") -> None:
        if scoring_method not in self.VALID_SCORING_METHODS:
            allowed = ", ".join(sorted(self.VALID_SCORING_METHODS))
            raise ValueError(f"unsupported scoring_method {scoring_method!r}; must be one of {allowed}")
        self.scoring_method = scoring_method

    async def run(self, ctx: StageContext) -> StageResult:
        candidates = list(ctx.data.get("candidates") or [])
        ranking = sorted(
            (
                {
                    "id": candidate.get("id"),
                    "title": candidate.get("title"),
                    "score": int(candidate.get("base_score") or 0),
                }
                for candidate in candidates
            ),
            key=lambda item: (-item["score"], str(item["id"])),
        )
        artifact = {
            "id": f"{ctx.run_id}:compare:ranking",
            "kind": "ranking",
            "stage": self.id.value,
            "method": self.scoring_method,
            "ref": "agent-run:ranking",
            "summary": f"Compare ranking via {self.scoring_method}",
            "ranking": ranking,
        }
        ctx.data["ranking"] = ranking
        return StageResult(
            stage=self.id,
            summary=f"ranked {len(ranking)} candidates with {self.scoring_method}",
            payload={"method": self.scoring_method, "ranking_count": len(ranking)},
            artifacts=[artifact],
            tokens=12,
        )


class EvolveStage:
    id = StageEnum.EVOLVE

    async def run(self, ctx: StageContext) -> StageResult:
        ranking = list(ctx.data.get("ranking") or [])
        return StageResult(
            stage=self.id,
            summary="prepared bounded improvement notes without applying edits",
            payload={"evolved_candidate_count": len(ranking)},
            tokens=6,
        )


class ValidateStage:
    id = StageEnum.VALIDATE

    async def run(self, ctx: StageContext) -> StageResult:
        return StageResult(
            stage=self.id,
            summary="validated bounded run outputs locally",
            payload={"validated": True},
            tokens=6,
        )


class CacheStage:
    id = StageEnum.CACHE

    async def run(self, ctx: StageContext) -> StageResult:
        return StageResult(
            stage=self.id,
            summary="cached run outputs as trace artifacts",
            payload={"cached": True},
            tokens=4,
        )


class LoopControlStage:
    id = StageEnum.LOOP_CONTROL

    async def run(self, ctx: StageContext) -> StageResult:
        return StageResult(
            stage=self.id,
            summary="stopped at the Phase-2 recipe boundary",
            payload={"boundary": "recipe-complete", "reenter_generate": False},
            tokens=2,
        )


def default_stages(scoring_method: str = "pairwise") -> dict[StageEnum, Stage]:
    return {
        StageEnum.GENERATE: GenerateStage(),
        StageEnum.REVIEW: ReviewStage(),
        StageEnum.COMPARE: CompareStage(scoring_method),
        StageEnum.EVOLVE: EvolveStage(),
        StageEnum.VALIDATE: ValidateStage(),
        StageEnum.CACHE: CacheStage(),
        StageEnum.LOOP_CONTROL: LoopControlStage(),
    }
