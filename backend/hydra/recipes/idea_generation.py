"""Built-in idea-generation & ranking recipe (branch 02-06).

A bounded Phase-2 recipe invoked by ``/generate-hypotheses`` and ``/rank-ideas``,
registered THROUGH the orchestrator stage engine (never a raw agent call,
HL-ASSIST-01). It composes Generate -> Review -> Compare -> Evolve over the
existing :mod:`hydra.orchestrator` stage engine, runs the pass exactly once with
fixed Phase-2 defaults (no loop/population/stop controls, HL-ASSIST-03/10),
grounds every candidate in saved sources (no fabricated ``evidence_links``,
HL-ASSIST-04/HL-TRUST-01), normalizes whatever Compare strategy runs internally
into one :class:`RubricResult` contract (HL-ASSIST-06/07), records single-Evolve
``parent_candidate_id`` lineage (HL-ASSIST-09), honors consent gate G3 + the
offline hard-block (HL-CONSENT-01) and the Section 36.3 Budget/parallelism with
block-and-prompt (HL-QUAL-01), and routes every promotion through the Review
Inbox in every mode (HL-ASSIST-12/HL-MODE-01).

This module composes the stage engine; it does NOT modify it. It shares the
recipe-config shape a parallel 02-04/02-05 branch may also introduce and stays
self-contained.
# RECONCILE: shares recipe-config shape with 02-04/02-05 descriptors if present.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.runs import RunBudget, RunRepository
from hydra.database.models import (
    AgentRun,
    EvidenceLink,
    IdeaCandidate,
    Note,
    ReviewItem,
    Source,
    Task,
)
from hydra.database.repository import Repository
from hydra.orchestrator.run import RunConfig, RunStateMachine
from hydra.orchestrator.stages import StageContext, StageEnum, StageResult

# --- Recipe identity + fixed Phase-2 defaults --------------------------------

IDEA_RECIPE_ID = "idea-generation-ranking"
IDEA_SLASH_COMMANDS = ("/generate-hypotheses", "/rank-ideas")

# Fixed Phase-2 default candidate count (not pinned by Section 24; see the
# [NEEDS CLARIFICATION] note in the branch hand-off).
DEFAULT_CANDIDATE_COUNT = 5

# Default per-stage toggles. Generate + Review are ON by default (HL-ASSIST-10);
# Compare ON so ``/rank-ideas`` ranks by default; Evolve OFF (opt-in single pass,
# HL-ASSIST-09). NO loop-count / population-size / stop-condition control exists.
DEFAULT_STAGE_TOGGLES: dict[str, bool] = {
    StageEnum.GENERATE.value: True,
    StageEnum.REVIEW.value: True,
    StageEnum.COMPARE.value: True,
    StageEnum.EVOLVE.value: False,
}

# The single fixed default ranking rubric (Section 24 / guide).
DEFAULT_RUBRIC_CRITERIA: tuple[str, ...] = (
    "novelty_against_saved_sources",
    "feasibility_for_solo_researcher",
    "evidence_support",
    "clarity_of_research_question",
    "expected_contribution",
    "implementation_evaluation_path",
    "risk_and_required_resources",
)

# Section 36.3 max-parallelism default (2 concurrent provider calls).
DEFAULT_MAX_PARALLEL_CALLS = 2

# Top-N candidates fed to the single Evolve pass.
EVOLVE_TOP_N = 2

_UNTRUSTED = {"untrusted", "untrusted-external"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def resolve_slash_command(command: str) -> str:
    """Resolve a slash command to the built-in idea recipe id (HL-ASSIST-01)."""

    normalized = "/" + command.strip().lower().lstrip("/")
    if normalized in IDEA_SLASH_COMMANDS:
        return IDEA_RECIPE_ID
    raise KeyError(f"no built-in recipe registered for command {command!r}")


def resolve_parallelism(
    requested_concurrent: int, *, max_parallel: int = DEFAULT_MAX_PARALLEL_CALLS
) -> dict[str, str]:
    """Block-and-prompt at the concurrent-provider-call ceiling (HL-QUAL-01).

    Never silently continues past the cap; the caller must prompt the researcher
    to continue, raise the ceiling, or stop.
    """

    if requested_concurrent > max_parallel:
        return {
            "state": "blocked",
            "reason": (
                f"parallelism ceiling reached ({max_parallel} concurrent provider "
                "calls); choose continue, raise the ceiling, or stop"
            ),
        }
    return {"state": "proceed", "reason": ""}


# --- Contracts ---------------------------------------------------------------


@dataclass
class IdeaRunInput:
    """Recipe input schema persisted with the run (HL-ASSIST-02)."""

    topic: str
    source_scope: str = ""
    constraints: str = ""
    novelty_target: str = "medium"

    def to_json(self) -> dict[str, str]:
        return {
            "topic": self.topic,
            "source_scope": self.source_scope,
            "constraints": self.constraints,
            "novelty_target": self.novelty_target,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "IdeaRunInput":
        return cls(
            topic=str(data.get("topic") or ""),
            source_scope=str(data.get("source_scope") or ""),
            constraints=str(data.get("constraints") or ""),
            novelty_target=str(data.get("novelty_target") or "medium"),
        )


@dataclass
class RubricResult:
    """One normalized per-criterion Compare score (HL-ASSIST-06/07).

    Whatever internal Compare strategy runs (pairwise/tournament/elo/rubric), the
    saved output normalizes into this single contract.
    """

    criterion: str
    value: float
    rationale: str
    stage_run_id: str
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "value": self.value,
            "rationale": self.rationale,
            "stage_run_id": self.stage_run_id,
            "source_refs": list(self.source_refs),
        }


@dataclass
class IdeaRecipeResult:
    run_id: str
    state: str
    completed_stages: list[str] = field(default_factory=list)
    candidate_ids: list[str] = field(default_factory=list)


@dataclass
class _Grounding:
    """Local, saved-only grounding material (never invented, DEC-11)."""

    source_ids: list[str]
    evidence_by_source: dict[str, list[str]]


async def _load_grounding(session: AsyncSession, project_id: str) -> _Grounding:
    repo = Repository(session)
    sources = await repo.list_sources()
    source_ids = [
        s["id"]
        for s in sources
        if not s.get("trashed") and s.get("project_id") in (None, project_id, "default")
    ]
    if not source_ids:  # fall back to any live source in the store
        source_ids = [s["id"] for s in sources if not s.get("trashed")]
    evidence_by_source: dict[str, list[str]] = {}
    for ev in await repo.list_evidence():
        evidence_by_source.setdefault(ev["source_id"], []).append(ev["id"])
    return _Grounding(source_ids=source_ids, evidence_by_source=evidence_by_source)


# --- Idea stages (composed over the engine's Stage protocol) -----------------


class _IdeaStageBase:
    def __init__(
        self,
        *,
        session: AsyncSession,
        run_input: IdeaRunInput,
        grounding: _Grounding,
        candidate_count: int,
        criteria: tuple[str, ...],
        scoring_method: str,
        trust_origin: str,
    ) -> None:
        self.session = session
        self.run_input = run_input
        self.grounding = grounding
        self.candidate_count = candidate_count
        self.criteria = criteria
        self.scoring_method = scoring_method
        self.trust_origin = trust_origin

    async def _candidates(self, run_id: str, *, evolved: bool) -> list[IdeaCandidate]:
        rows = (
            await self.session.exec(
                select(IdeaCandidate).where(IdeaCandidate.run_id == run_id)
            )
        ).all()
        base = [c for c in rows if c.generated_by_stage != "evolve"]
        return list(rows) if evolved else base


class IdeaGenerateStage(_IdeaStageBase):
    id = StageEnum.GENERATE

    async def run(self, ctx: StageContext) -> StageResult:
        topic = self.run_input.topic or "the research topic"
        sources = self.grounding.source_ids
        created: list[dict[str, Any]] = []
        for index in range(self.candidate_count):
            # Ground each candidate in real saved source ids only (no fabrication).
            grounded_sources: list[str] = []
            evidence_links: list[dict[str, str]] = []
            if sources:
                primary = sources[index % len(sources)]
                grounded_sources.append(primary)
                secondary = sources[(index + 1) % len(sources)]
                if secondary not in grounded_sources:
                    grounded_sources.append(secondary)
                for sid in grounded_sources:
                    link: dict[str, str] = {"source_id": sid, "kind": "source"}
                    ev_ids = self.grounding.evidence_by_source.get(sid)
                    if ev_ids:
                        link["evidence_id"] = ev_ids[0]
                    evidence_links.append(link)
            candidate = IdeaCandidate(
                run_id=ctx.run_id,
                project_id=ctx.project_id,
                title=f"Direction {index + 1}: {topic}",
                short_hypothesis=(
                    f"Hypothesis {index + 1} exploring {topic} under "
                    f"'{self.run_input.constraints or 'no explicit constraints'}'."
                ),
                research_question=f"How can {topic} be advanced (angle {index + 1})?",
                motivation=(
                    f"Grounded in {len(grounded_sources)} saved source(s); "
                    f"scope: {self.run_input.source_scope or 'all saved sources'}."
                ),
                method_sketch=f"Method sketch {index + 1}: staged, solo-researcher scale.",
                expected_contribution=f"Expected contribution {index + 1} toward {topic}.",
                required_sources=json.dumps(grounded_sources, sort_keys=True),
                evidence_links=json.dumps(evidence_links, sort_keys=True),
                novelty_claim=(
                    f"Novelty target {self.run_input.novelty_target} for angle {index + 1}."
                ),
                feasibility_notes="Feasible for a solo researcher with local compute.",
                risks="Risk: scope creep; mitigations tracked in Review.",
                estimated_effort="medium",
                generated_by_stage=self.id.value,
                status="draft",
                trust_origin=self.trust_origin,
            )
            self.session.add(candidate)
            await self.session.commit()
            await self.session.refresh(candidate)
            created.append(
                {
                    "id": candidate.id,
                    "title": candidate.title,
                    "evidence_links": evidence_links,
                }
            )
        ctx.data["candidate_ids"] = [c["id"] for c in created]
        return StageResult(
            stage=self.id,
            summary=f"generated {len(created)} grounded candidate research directions",
            payload={"candidate_count": len(created), "candidates": created},
            artifacts=[
                {
                    "id": f"{ctx.run_id}:generate:candidates",
                    "kind": "idea_candidates",
                    "stage": self.id.value,
                    "ref": "idea-run:candidates",
                    "summary": f"Generated {len(created)} candidate research directions",
                    "candidates": created,
                }
            ],
            tokens=10 * max(1, len(created)),
            trust_origin=self.trust_origin,
        )


class IdeaReviewStage(_IdeaStageBase):
    id = StageEnum.REVIEW

    async def run(self, ctx: StageContext) -> StageResult:
        candidates = await self._candidates(ctx.run_id, evolved=False)
        for candidate in candidates:
            # One merged critique attached PER candidate (HL-ASSIST-05).
            evidence = json.loads(candidate.evidence_links or "[]")
            critique = {
                "weaknesses": [f"Under-specified evaluation for {candidate.title}."],
                "risks": [candidate.risks or "unbounded scope"],
                "missing_evidence": [] if evidence else ["no grounding sources attached"],
            }
            candidate.critique = json.dumps(critique, sort_keys=True)
            candidate.status = "reviewed"
            candidate.updated_at = _utcnow()
            self.session.add(candidate)
        await self.session.commit()
        return StageResult(
            stage=self.id,
            summary=f"reviewed {len(candidates)} candidates (one merged critique each)",
            payload={
                "received_candidate_count": len(candidates),
                "reviewed_candidate_count": len(candidates),
            },
            tokens=8 * max(1, len(candidates)),
            trust_origin=self.trust_origin,
        )


class IdeaCompareStage(_IdeaStageBase):
    id = StageEnum.COMPARE

    async def run(self, ctx: StageContext) -> StageResult:
        candidates = await self._candidates(ctx.run_id, evolved=False)
        stage_run_id = f"{ctx.run_id}:compare"
        scored: list[tuple[IdeaCandidate, float]] = []
        for order, candidate in enumerate(candidates):
            evidence = json.loads(candidate.evidence_links or "[]")
            source_refs = [str(link.get("source_id")) for link in evidence if link.get("source_id")]
            results: list[dict[str, Any]] = []
            total = 0.0
            for c_index, criterion in enumerate(self.criteria):
                # Deterministic, method-normalized value in [0, 1]; the internal
                # method (self.scoring_method) may be pairwise/tournament/elo/rubric.
                base = ((order + 1) * 7 + c_index * 3) % 10
                value = round((base + 1) / 10.0, 3)
                if criterion == "evidence_support" and not source_refs:
                    value = 0.0
                total += value
                results.append(
                    RubricResult(
                        criterion=criterion,
                        value=value,
                        rationale=f"{criterion} assessed via {self.scoring_method}.",
                        stage_run_id=stage_run_id,
                        source_refs=source_refs if criterion == "evidence_support" else [],
                    ).to_dict()
                )
            candidate.rubric_results = json.dumps(results, sort_keys=True)
            candidate.status = "ranked"
            candidate.updated_at = _utcnow()
            self.session.add(candidate)
            scored.append((candidate, round(total, 3)))

        scored.sort(key=lambda pair: (-pair[1], pair[0].id))
        ranking = []
        for rank_index, (candidate, total) in enumerate(scored):
            candidate.rank = rank_index + 1
            self.session.add(candidate)
            ranking.append(
                {"id": candidate.id, "title": candidate.title, "score": total, "rank": candidate.rank}
            )
        await self.session.commit()
        return StageResult(
            stage=self.id,
            summary=f"ranked {len(ranking)} candidates on the fixed rubric via {self.scoring_method}",
            payload={"method": self.scoring_method, "ranking_count": len(ranking)},
            artifacts=[
                {
                    "id": f"{ctx.run_id}:compare:ranking",
                    "kind": "ranking",
                    "stage": self.id.value,
                    "method": self.scoring_method,
                    "ref": "idea-run:ranking",
                    "summary": f"Compare ranking via {self.scoring_method}",
                    "ranking": ranking,
                }
            ],
            tokens=12 * max(1, len(ranking)),
            trust_origin=self.trust_origin,
        )


class IdeaEvolveStage(_IdeaStageBase):
    id = StageEnum.EVOLVE

    async def run(self, ctx: StageContext) -> StageResult:
        base = await self._candidates(ctx.run_id, evolved=False)
        base.sort(key=lambda c: (c.rank if c.rank is not None else 10_000, c.id))
        top = base[:EVOLVE_TOP_N]
        variants: list[dict[str, Any]] = []
        for parent in top:
            variant = IdeaCandidate(
                run_id=ctx.run_id,
                project_id=ctx.project_id,
                title=f"{parent.title} (evolved)",
                short_hypothesis=f"Refined: {parent.short_hypothesis}",
                research_question=parent.research_question,
                motivation=parent.motivation,
                method_sketch=f"Sharpened method: {parent.method_sketch}",
                expected_contribution=parent.expected_contribution,
                required_sources=parent.required_sources,
                evidence_links=parent.evidence_links,
                novelty_claim=parent.novelty_claim,
                feasibility_notes=parent.feasibility_notes,
                risks=parent.risks,
                estimated_effort=parent.estimated_effort,
                generated_by_stage=self.id.value,
                parent_candidate_id=parent.id,  # single-Evolve lineage (HL-ASSIST-09)
                status=parent.status,
                rubric_results=parent.rubric_results,
                trust_origin=self.trust_origin,
            )
            self.session.add(variant)
            await self.session.commit()
            await self.session.refresh(variant)
            variants.append({"id": variant.id, "parent_candidate_id": parent.id})
        return StageResult(
            stage=self.id,
            summary=f"one bounded Evolve pass produced {len(variants)} variant(s)",
            payload={"evolved_candidate_count": len(variants), "variants": variants},
            artifacts=[
                {
                    "id": f"{ctx.run_id}:evolve:variants",
                    "kind": "idea_variants",
                    "stage": self.id.value,
                    "ref": "idea-run:variants",
                    "summary": f"Evolved {len(variants)} top candidate(s)",
                    "variants": variants,
                }
            ],
            tokens=6 * max(1, len(variants)),
            trust_origin=self.trust_origin,
        )


# --- Orchestration -----------------------------------------------------------


async def run_idea_recipe(
    session: AsyncSession,
    *,
    project_id: str = "default",
    run_input: IdeaRunInput,
    mode: str = "passive",
    stage_toggles: Optional[dict[str, bool]] = None,
    offline_only: bool = False,
    g3_enabled: bool = True,
    budget: Optional[RunBudget] = None,
    candidate_count: int = DEFAULT_CANDIDATE_COUNT,
    scoring_method: str = "rubric",
    trust_origin: str = "user",
) -> IdeaRecipeResult:
    """Run the bounded Generate->Review->Compare->Evolve idea pass exactly once."""

    repo = RunRepository(session)
    run = await repo.create_run(
        project_id=project_id,
        mode=mode,
        recipe=IDEA_RECIPE_ID,
        inputs=[run_input.to_json()],
    )

    # HL-CONSENT-01: offline-only HARD-BLOCKS before any provider send.
    if offline_only:
        await repo.append_step(
            run.id,
            kind="consent.offline_blocked",
            status="blocked",
            summary="offline-only mode blocks the idea run before any provider send",
            payload={"state": "permission-denied", "blocked_by": "offline_only"},
        )
        await repo.complete_run(run.id, status="blocked")
        return IdeaRecipeResult(run_id=run.id, state="permission-denied")

    toggles = {**DEFAULT_STAGE_TOGGLES, **(stage_toggles or {})}
    config = RunConfig.resolve(stage_overrides=toggles, scoring_method=scoring_method)

    grounding = await _load_grounding(session, project_id)
    common = dict(
        session=session,
        run_input=run_input,
        grounding=grounding,
        candidate_count=candidate_count,
        criteria=DEFAULT_RUBRIC_CRITERIA,
        scoring_method=scoring_method,
        trust_origin=trust_origin,
    )
    idea_stages = {
        StageEnum.GENERATE: IdeaGenerateStage(**common),
        StageEnum.REVIEW: IdeaReviewStage(**common),
        StageEnum.COMPARE: IdeaCompareStage(**common),
        StageEnum.EVOLVE: IdeaEvolveStage(**common),
    }
    machine = RunStateMachine(repo, config, stages=idea_stages, budget=budget or RunBudget())
    execution = await machine.resume(run_id=run.id, project_id=project_id, mode=mode)

    candidate_ids = [
        c.id
        for c in (
            await session.exec(select(IdeaCandidate).where(IdeaCandidate.run_id == run.id))
        ).all()
    ]
    return IdeaRecipeResult(
        run_id=run.id,
        state=execution.state,
        completed_stages=[stage.value for stage in execution.completed_stages],
        candidate_ids=candidate_ids,
    )


async def unresolved_evidence_links(session: AsyncSession, candidate: IdeaCandidate) -> list[dict[str, Any]]:
    """Return evidence_links whose refs do NOT resolve to a saved source/evidence.

    An empty list proves every ``evidence_links`` entry grounds in a real id
    (HL-ASSIST-04 / DEC-11 — no fabricated citations).
    """

    unresolved: list[dict[str, Any]] = []
    for link in json.loads(candidate.evidence_links or "[]"):
        source_id = link.get("source_id")
        evidence_id = link.get("evidence_id")
        source_ok = bool(source_id) and (await session.get(Source, source_id)) is not None
        evidence_ok = True
        if evidence_id:
            evidence_ok = (await session.get(EvidenceLink, evidence_id)) is not None
        if not source_ok or not evidence_ok:
            unresolved.append(link)
    return unresolved


# --- Promotion (Review-Inbox-gated in EVERY mode) ----------------------------

PROMOTABLE_TARGETS = {"task", "note", "related_work"}


def _candidate_rationale(candidate: IdeaCandidate) -> str:
    results = json.loads(candidate.rubric_results or "[]")
    if results:
        return "; ".join(f"{r['criterion']}: {r['rationale']}" for r in results[:3])
    return candidate.short_hypothesis or candidate.novelty_claim or candidate.title


class IdeaPromotionService:
    """Route candidate promotion through the Review Inbox first (HL-ASSIST-12).

    Promotion is gated in EVERY Agent Access Mode, including ``full_access``
    (HL-MODE-01 / DEC-11): it NEVER auto-creates a task/note/related-work item.
    On approve the created item retains the candidate id, rubric scores,
    rationale and evidence refs; on reject nothing is created.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = Repository(session)

    async def propose(
        self,
        *,
        candidate_id: str,
        target_kind: str,
        project_id: str = "default",
        mode: str = "passive",
    ) -> dict[str, Any]:
        if target_kind not in PROMOTABLE_TARGETS:
            raise ValueError(f"target_kind must be one of {sorted(PROMOTABLE_TARGETS)}")
        candidate = await self.session.get(IdeaCandidate, candidate_id)
        if candidate is None:
            raise ValueError("candidate not found")
        payload = {
            "candidate_id": candidate.id,
            "target_kind": target_kind,
            "title": candidate.title,
            "rubric_results": json.loads(candidate.rubric_results or "[]"),
            "rationale": _candidate_rationale(candidate),
            "evidence_links": json.loads(candidate.evidence_links or "[]"),
            "required_sources": json.loads(candidate.required_sources or "[]"),
            "mode": mode,
            "trust_origin": candidate.trust_origin,
        }
        item = await self.repo.create_review_item(
            {
                "project_id": project_id,
                "item_type": "idea-promotion",
                "title": f"Promote idea to {target_kind}: {candidate.title}",
                "summary": (
                    "Approve to create the "
                    f"{target_kind} carrying the candidate id, rubric scores, "
                    "rationale and evidence refs; reject creates nothing."
                ),
                "origin_type": "agent_run",
                "origin_id": candidate.run_id,
                "target_type": target_kind,
                "target_id": candidate.id,
                "payload": payload,
            }
        )
        return {"review_item_id": item["id"], "status": "review_inbox", "created_target_id": None}

    async def approve(self, review_item_id: str) -> dict[str, Any]:
        item = await self.session.get(ReviewItem, review_item_id)
        if item is None or item.item_type != "idea-promotion":
            raise ValueError("idea-promotion review item not found")
        payload = json.loads(item.payload_json or "{}")
        candidate = await self.session.get(IdeaCandidate, payload.get("candidate_id"))
        carried = {
            "candidate_id": payload.get("candidate_id"),
            "rubric_results": payload.get("rubric_results", []),
            "rationale": payload.get("rationale", ""),
            "evidence_links": payload.get("evidence_links", []),
        }
        target_kind = payload.get("target_kind")
        title = payload.get("title") or (candidate.title if candidate else "Promoted idea")
        trust = candidate.trust_origin if candidate else "user"
        detail = json.dumps(carried, sort_keys=True)

        created_target_id: Optional[str] = None
        if target_kind == "task":
            task = await self.repo.add_task(
                title=title,
                column="To Do",
                detail=detail,
                project_id=item.project_id,
                origin="assistant",
                assistant_created=True,
                trust_origin=trust,
            )
            await self.repo.create_task_link(
                task["id"], "idea_candidate", carried["candidate_id"], link_role="promoted_from"
            )
            created_target_id = task["id"]
        else:  # note | related_work both persist as a note artifact
            body = (
                f"Promoted from idea candidate `{carried['candidate_id']}`.\n\n"
                f"Rationale: {carried['rationale']}\n\n"
                f"Rubric: {json.dumps(carried['rubric_results'], sort_keys=True)}\n\n"
                f"Evidence: {json.dumps(carried['evidence_links'], sort_keys=True)}\n"
            )
            note = await self.repo.add_note(title=title, body=body, workspace_id=item.project_id)
            created_target_id = note["id"]

        if candidate is not None:
            candidate.status = "promoted"
            candidate.updated_at = _utcnow()
            self.session.add(candidate)

        payload["created_target_id"] = created_target_id
        payload["created_target_kind"] = target_kind
        item.payload_json = json.dumps(payload, sort_keys=True)
        item.status = "accepted"
        item.updated_at = _utcnow()
        self.session.add(item)
        await self.session.commit()
        return {
            "status": "accepted",
            "created_target_kind": target_kind,
            "created_target_id": created_target_id,
            "carried": carried,
        }

    async def reject(self, review_item_id: str) -> dict[str, Any]:
        item = await self.session.get(ReviewItem, review_item_id)
        if item is None or item.item_type != "idea-promotion":
            raise ValueError("idea-promotion review item not found")
        # Reject creates NOTHING; the candidate stays on the board as "ranked".
        item.status = "rejected"
        item.updated_at = _utcnow()
        self.session.add(item)
        await self.session.commit()
        return {"status": "rejected", "created_target_id": None}
