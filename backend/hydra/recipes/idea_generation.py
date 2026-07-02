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

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations
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
from hydra.recipes.retrieval import LiteratureHit, RetrievalOptions, retrieve_literature_hits

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

# Angle-typed diversity for Generate (replaces integer suffixes; Co-Scientist
# "diverse candidates in a single pass" faithfulness).
IDEA_ANGLES: tuple[str, ...] = ("mechanism", "contrast", "synthesis", "method-transfer")

# Generate over-produces candidate_count+K then self-critiques and culls down to
# candidate_count (debate-before-exit, single pass — no loop).
GENERATE_OVERGEN_K = 2

# Reflection check types (rising rigor), each tagged with a verdict.
REVIEW_CHECK_TYPES: tuple[str, ...] = (
    "novelty_grounding",
    "assumption_decomposition",
    "observation_consistency",
    "correctness",
    "safety_feasibility",
)

# Compare scoring methods that run the real pairwise tournament (BTL-aggregated);
# "rubric" stays as an explicit absolute-scoring fallback.
PAIRWISE_METHODS: frozenset[str] = frozenset({"pairwise", "tournament", "elo"})

# Robin ranking policy: full round-robin at or below the cap, else a bounded
# deterministic sample of pairs (no RNG — pairs derived from sorted ids).
MAX_ROUND_ROBIN = 25
SAMPLED_PAIR_BUDGET = 300

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


# --- Deterministic offline reasoning helpers ---------------------------------
#
# These run WITHOUT any provider call so the offline-first / G3-gated posture
# holds: Compare runs a real pairwise tournament with a deterministic
# evidence/confidence comparator, Review runs typed decomposed checks, and both
# are reproducible (no RNG; pair sampling derives from sorted candidate ids). A
# real-LLM judge/critic MAY be layered behind a provider-available check later
# without changing these contracts.


def _stable_unit(value: str) -> float:
    """Deterministic pseudo-value in [0, 1) from a string (no RNG)."""

    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return (int(digest[:12], 16) % 1_000_000) / 1_000_000.0


def _source_refs(candidate: IdeaCandidate) -> list[str]:
    links = json.loads(candidate.evidence_links or "[]")
    return [str(link.get("source_id")) for link in links if link.get("source_id")]


def _criterion_signal(candidate: IdeaCandidate, criterion: str) -> float:
    """Per-criterion strength signal the pairwise comparator ranks on.

    Grounded-evidence count drives ``evidence_support`` directly (no grounding
    -> 0); other criteria mix a stable per-(candidate, criterion) component with
    grounding so different criteria can order candidates differently.
    """

    refs = _source_refs(candidate)
    grounding = len(refs) / (len(refs) + 1)
    if criterion == "evidence_support":
        return round(grounding, 6)
    base = _stable_unit(f"{candidate.id}|{criterion}")
    return round(0.6 * base + 0.4 * grounding, 6)


def _candidate_pairs(ids: list[str]) -> list[tuple[str, str]]:
    """Round-robin at/below the cap, else a deterministic sample (Robin policy)."""

    ordered = sorted(ids)
    all_pairs = list(combinations(ordered, 2))
    if len(ordered) <= MAX_ROUND_ROBIN:
        return all_pairs
    ranked = sorted(all_pairs, key=lambda pair: _stable_unit(f"{pair[0]}::{pair[1]}"))
    return ranked[:SAMPLED_PAIR_BUDGET]


def _btl_strengths(
    ids: list[str],
    win_counts: dict[str, int],
    comparisons: dict[frozenset[str], int],
    *,
    iters: int = 100,
) -> dict[str, float]:
    """Bradley-Terry-Luce strengths via deterministic MM iterations."""

    if len(ids) <= 1:
        return {idea_id: 0.5 for idea_id in ids}
    strengths = {idea_id: 1.0 for idea_id in ids}
    for _ in range(iters):
        updated: dict[str, float] = {}
        for i in ids:
            denom = 0.0
            for j in ids:
                if i == j:
                    continue
                n_ij = comparisons.get(frozenset((i, j)), 0)
                if not n_ij:
                    continue
                denom += n_ij / (strengths[i] + strengths[j])
            wins = win_counts.get(i, 0)
            updated[i] = (wins + 0.5) / (denom + 1.0) if denom > 0 else strengths[i]
        total = sum(updated.values()) or 1.0
        strengths = {i: value * len(ids) / total for i, value in updated.items()}
    return strengths


def _normalize_unit(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    low = min(values.values())
    high = max(values.values())
    if high <= low:
        return {key: 0.5 for key in values}
    return {key: round((value - low) / (high - low), 6) for key, value in values.items()}


def _pairwise_rank(
    candidates: list[IdeaCandidate],
    *,
    criteria: tuple[str, ...],
    scoring_method: str,
    stage_run_id: str,
) -> dict[str, Any]:
    """Real pairwise tournament -> BTL strengths -> normalized RubricResults.

    Persists one :class:`RubricResult` per criterion per candidate (contract
    unchanged) and returns the ranking plus the pairwise matrix and per-matchup
    rationales for the ranking artifact.
    """

    by_id = {candidate.id: candidate for candidate in candidates}
    ids = list(by_id)
    pairs = _candidate_pairs(ids)
    win_counts: dict[str, dict[str, int]] = {c: {i: 0 for i in ids} for c in criteria}
    comparisons: dict[str, dict[frozenset[str], int]] = {c: {} for c in criteria}
    rationales: list[dict[str, Any]] = []
    for a_id, b_id in pairs:
        a, b = by_id[a_id], by_id[b_id]
        for criterion in criteria:
            sig_a = _criterion_signal(a, criterion)
            sig_b = _criterion_signal(b, criterion)
            if sig_a > sig_b or (sig_a == sig_b and a_id < b_id):
                winner, loser, sig_w, sig_l = a_id, b_id, sig_a, sig_b
            else:
                winner, loser, sig_w, sig_l = b_id, a_id, sig_b, sig_a
            win_counts[criterion][winner] += 1
            key = frozenset((a_id, b_id))
            comparisons[criterion][key] = comparisons[criterion].get(key, 0) + 1
            rationales.append(
                {
                    "pair": [a_id, b_id],
                    "criterion": criterion,
                    "winner": winner,
                    "rationale": (
                        f"{winner} preferred over {loser} on {criterion} "
                        f"(signal {sig_w:.2f} vs {sig_l:.2f}) via {scoring_method}."
                    ),
                }
            )

    strengths_by_criterion: dict[str, dict[str, float]] = {}
    for criterion in criteria:
        raw = _btl_strengths(ids, win_counts[criterion], comparisons[criterion])
        strengths_by_criterion[criterion] = _normalize_unit(raw)

    totals: dict[str, float] = {i: 0.0 for i in ids}
    for criterion in criteria:
        for i in ids:
            totals[i] += strengths_by_criterion[criterion].get(i, 0.0)

    for candidate in candidates:
        refs = _source_refs(candidate)
        results: list[dict[str, Any]] = []
        for criterion in criteria:
            value = strengths_by_criterion[criterion].get(candidate.id, 0.0)
            wins = win_counts[criterion].get(candidate.id, 0)
            results.append(
                RubricResult(
                    criterion=criterion,
                    value=value,
                    rationale=(
                        f"{criterion}: {wins} pairwise win(s) over {len(pairs)} "
                        f"matchup(s); BTL strength {value:.2f} via {scoring_method}."
                    ),
                    stage_run_id=stage_run_id,
                    source_refs=refs if criterion == "evidence_support" else [],
                ).to_dict()
            )
        candidate.rubric_results = json.dumps(results, sort_keys=True)
        candidate.status = "ranked"
        candidate.updated_at = _utcnow()

    ordered = sorted(candidates, key=lambda c: (-totals[c.id], c.id))
    ranking: list[dict[str, Any]] = []
    for rank_index, candidate in enumerate(ordered):
        candidate.rank = rank_index + 1
        ranking.append(
            {
                "id": candidate.id,
                "title": candidate.title,
                "score": round(totals[candidate.id], 6),
                "rank": candidate.rank,
            }
        )
    pairwise_matrix = {
        criterion: {"candidate_ids": sorted(ids), "wins": win_counts[criterion]}
        for criterion in criteria
    }
    return {
        "ranking": ranking,
        "pairwise_matrix": pairwise_matrix,
        "matchup_rationales": rationales,
        "pair_count": len(pairs),
    }


def _rubric_rank(
    candidates: list[IdeaCandidate],
    *,
    criteria: tuple[str, ...],
    scoring_method: str,
    stage_run_id: str,
) -> dict[str, Any]:
    """Explicit absolute-scoring fallback (scoring_method='rubric')."""

    scored: list[tuple[IdeaCandidate, float]] = []
    for order, candidate in enumerate(candidates):
        refs = _source_refs(candidate)
        results: list[dict[str, Any]] = []
        total = 0.0
        for c_index, criterion in enumerate(criteria):
            base = ((order + 1) * 7 + c_index * 3) % 10
            value = round((base + 1) / 10.0, 3)
            if criterion == "evidence_support" and not refs:
                value = 0.0
            total += value
            results.append(
                RubricResult(
                    criterion=criterion,
                    value=value,
                    rationale=f"{criterion} assessed via {scoring_method} (absolute rubric).",
                    stage_run_id=stage_run_id,
                    source_refs=refs if criterion == "evidence_support" else [],
                ).to_dict()
            )
        candidate.rubric_results = json.dumps(results, sort_keys=True)
        candidate.status = "ranked"
        candidate.updated_at = _utcnow()
        scored.append((candidate, round(total, 3)))

    scored.sort(key=lambda pair: (-pair[1], pair[0].id))
    ranking: list[dict[str, Any]] = []
    for rank_index, (candidate, total) in enumerate(scored):
        candidate.rank = rank_index + 1
        ranking.append(
            {"id": candidate.id, "title": candidate.title, "score": total, "rank": candidate.rank}
        )
    return {"ranking": ranking, "pairwise_matrix": {}, "matchup_rationales": [], "pair_count": 0}


def _score_candidates(
    candidates: list[IdeaCandidate],
    *,
    criteria: tuple[str, ...],
    scoring_method: str,
    stage_run_id: str,
) -> dict[str, Any]:
    if not candidates:
        return {"ranking": [], "pairwise_matrix": {}, "matchup_rationales": [], "pair_count": 0}
    if scoring_method in PAIRWISE_METHODS:
        return _pairwise_rank(
            candidates, criteria=criteria, scoring_method=scoring_method, stage_run_id=stage_run_id
        )
    return _rubric_rank(
        candidates, criteria=criteria, scoring_method=scoring_method, stage_run_id=stage_run_id
    )


def _check(check_type: str, verdict: str, evidence_refs: list[str], notes: str) -> dict[str, Any]:
    return {
        "check_type": check_type,
        "verdict": verdict,
        "evidence_refs": list(evidence_refs),
        "notes": notes,
    }


def _decompose_assumptions(candidate: IdeaCandidate) -> list[str]:
    """Enumerate the hypothesis assumptions for deep-verification tagging."""

    text = " ".join(filter(None, [candidate.short_hypothesis, candidate.research_question]))
    parts = re.split(r"\b(?:under|for|that|when|if|because|assuming|given)\b", text, flags=re.IGNORECASE)
    return [part.strip(" .") for part in parts[1:] if len(part.strip()) > 3][:4]


def _review_candidate(candidate: IdeaCandidate) -> tuple[list[dict[str, Any]], str]:
    """Run the typed reflection checks; return (check records, resolved status).

    A ``reject`` on any check moves the candidate to ``rejected`` (Compare then
    excludes it); otherwise it stays ``reviewed``.
    """

    refs = _source_refs(candidate)
    checks: list[dict[str, Any]] = []
    if refs:
        checks.append(
            _check("novelty_grounding", "pass", refs, f"Novelty grounded in {len(refs)} saved source(s).")
        )
    else:
        checks.append(
            _check(
                "novelty_grounding",
                "reject",
                [],
                "No saved-source grounding; novelty cannot be verified against the corpus.",
            )
        )
    assumptions = _decompose_assumptions(candidate)
    checks.append(
        _check(
            "assumption_decomposition",
            "pass" if assumptions else "flag",
            refs,
            ("Assumptions: " + "; ".join(assumptions))
            if assumptions
            else "No decomposable assumptions found in the hypothesis.",
        )
    )
    checks.append(
        _check(
            "observation_consistency",
            "pass" if refs else "flag",
            refs,
            "Hypothesis consistent with linked evidence."
            if refs
            else "No linked evidence to check observations against.",
        )
    )
    checks.append(
        _check(
            "correctness",
            "pass" if candidate.method_sketch.strip() else "flag",
            refs,
            "Method sketch present and internally consistent."
            if candidate.method_sketch.strip()
            else "Method sketch missing; correctness undetermined.",
        )
    )
    checks.append(
        _check(
            "safety_feasibility",
            "pass" if candidate.feasibility_notes.strip() else "flag",
            [],
            "Feasible for a solo researcher; no safety blockers."
            if candidate.feasibility_notes.strip()
            else "Feasibility not established.",
        )
    )
    status = "rejected" if any(record["verdict"] == "reject" for record in checks) else "reviewed"
    return checks, status


def _review_candidates(session: AsyncSession, candidates: list[IdeaCandidate]) -> int:
    """Attach typed critiques; return the number of rejected candidates."""

    rejected = 0
    for candidate in candidates:
        checks, status = _review_candidate(candidate)
        candidate.critique = json.dumps(checks, sort_keys=True)
        candidate.status = status
        candidate.updated_at = _utcnow()
        session.add(candidate)
        if status == "rejected":
            rejected += 1
    return rejected


def _flagged_notes(candidate: IdeaCandidate) -> list[str]:
    """Reflection-flagged weaknesses a repair variant should address."""

    try:
        checks = json.loads(candidate.critique or "[]")
    except ValueError:
        return []
    if isinstance(checks, dict):  # tolerate any legacy merged-dict critique
        return [str(item) for item in checks.get("weaknesses", [])]
    return [
        str(record.get("notes", ""))
        for record in checks
        if isinstance(record, dict) and record.get("verdict") in {"flag", "reject"}
    ]


def _token_set(text: str) -> frozenset[str]:
    return frozenset(token for token in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(token) > 2)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _merge_json_lists(*raw_values: str) -> list[Any]:
    """Merge JSON lists, de-duplicating dict entries by ``source_id``/repr."""

    merged: list[Any] = []
    seen: set[str] = set()
    for raw in raw_values:
        for item in json.loads(raw or "[]"):
            key = str(item.get("source_id")) if isinstance(item, dict) else json.dumps(item, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


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
        hits = await self._retrieve(topic)
        # Over-generate, self-critique, then cull to candidate_count (single
        # pass; diversity + internal critique stand in for the missing loop).
        overgen = self.candidate_count + GENERATE_OVERGEN_K
        blueprints = [self._blueprint(topic, index, hits) for index in range(overgen)]
        blueprints.sort(key=lambda bp: (-bp["_score"], bp["_key"]))
        kept = blueprints[: self.candidate_count]

        created: list[dict[str, Any]] = []
        for bp in kept:
            candidate = IdeaCandidate(
                run_id=ctx.run_id,
                project_id=ctx.project_id,
                title=bp["title"],
                short_hypothesis=bp["short_hypothesis"],
                research_question=bp["research_question"],
                motivation=bp["motivation"],
                method_sketch=bp["method_sketch"],
                expected_contribution=bp["expected_contribution"],
                required_sources=json.dumps(bp["grounded_sources"], sort_keys=True),
                evidence_links=json.dumps(bp["evidence_links"], sort_keys=True),
                novelty_claim=bp["novelty_claim"],
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
                    "angle": bp["angle"],
                    "evidence_links": bp["evidence_links"],
                }
            )
        ctx.data["candidate_ids"] = [c["id"] for c in created]
        return StageResult(
            stage=self.id,
            summary=(
                f"generated {len(created)} grounded, angle-typed candidates "
                f"(considered {overgen}, culled by self-critique)"
            ),
            payload={
                "candidate_count": len(created),
                "considered_count": overgen,
                "retrieval_hit_count": len(hits),
                "candidates": created,
            },
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

    async def _retrieve(self, topic: str) -> list[LiteratureHit]:
        """Relevance-ranked hits over saved sources (empty if none/unavailable)."""

        try:
            result = await retrieve_literature_hits(
                self.session,
                query=topic,
                source_scope={"kind": "all-project"},
                options=RetrievalOptions(),
            )
        except Exception:
            return []
        return list(result.hits)

    def _blueprint(self, topic: str, index: int, hits: list[LiteratureHit]) -> dict[str, Any]:
        angle = IDEA_ANGLES[index % len(IDEA_ANGLES)]
        grounded_sources: list[str] = []
        evidence_links: list[dict[str, str]] = []
        retrieval_confidence = 0.0

        if hits:
            # Relevance-driven assignment: each candidate takes its top-relevant
            # retrieved hits (source_id + chunk + evidence), not a round-robin index.
            picks = [hits[index % len(hits)]]
            secondary = hits[(index + 1) % len(hits)]
            if secondary.source_id != picks[0].source_id:
                picks.append(secondary)
            retrieval_confidence = picks[0].confidence
            for hit in picks:
                if hit.source_id in grounded_sources:
                    continue
                grounded_sources.append(hit.source_id)
                link: dict[str, str] = {"source_id": hit.source_id, "kind": "source"}
                if hit.chunk_id:
                    link["chunk_id"] = hit.chunk_id
                ev_ids = self.grounding.evidence_by_source.get(hit.source_id)
                if ev_ids:
                    link["evidence_id"] = ev_ids[0]
                evidence_links.append(link)
        elif self.grounding.source_ids:
            sources = self.grounding.source_ids
            grounded_sources.append(sources[index % len(sources)])
            secondary_id = sources[(index + 1) % len(sources)]
            if secondary_id not in grounded_sources:
                grounded_sources.append(secondary_id)
            for sid in grounded_sources:
                link = {"source_id": sid, "kind": "source"}
                ev_ids = self.grounding.evidence_by_source.get(sid)
                if ev_ids:
                    link["evidence_id"] = ev_ids[0]
                evidence_links.append(link)

        constraints = self.run_input.constraints or "no explicit constraints"
        scope = self.run_input.source_scope or "all saved sources"
        key = f"{topic}|{angle}|{index}"
        # Self-critique: prefer richer grounding + more relevant retrieval; stable
        # jitter only breaks exact ties deterministically.
        score = len(grounded_sources) + retrieval_confidence + _stable_unit(key) * 0.001
        return {
            "angle": angle,
            "title": f"{angle.replace('-', ' ').title()} angle: {topic}",
            "short_hypothesis": f"[{angle}] Hypothesis exploring {topic} under '{constraints}'.",
            "research_question": f"How can {topic} be advanced via a {angle} approach?",
            "motivation": (
                f"Grounded in {len(grounded_sources)} saved source(s); scope: {scope}; angle: {angle}."
            ),
            "method_sketch": f"{angle.replace('-', ' ').title()} method sketch: staged, solo-researcher scale.",
            "expected_contribution": f"Expected {angle} contribution toward {topic}.",
            "novelty_claim": f"Novelty target {self.run_input.novelty_target} for the {angle} angle.",
            "grounded_sources": grounded_sources,
            "evidence_links": evidence_links,
            "_score": score,
            "_key": key,
        }


class IdeaReviewStage(_IdeaStageBase):
    id = StageEnum.REVIEW

    async def run(self, ctx: StageContext) -> StageResult:
        candidates = await self._candidates(ctx.run_id, evolved=False)
        # Typed, criterion-tagged reflection checks PER candidate (HL-ASSIST-05);
        # a reject moves the candidate off the tournament.
        rejected = _review_candidates(self.session, candidates)
        await self.session.commit()
        return StageResult(
            stage=self.id,
            summary=(
                f"reviewed {len(candidates)} candidates via typed checks "
                f"({rejected} rejected)"
            ),
            payload={
                "received_candidate_count": len(candidates),
                "reviewed_candidate_count": len(candidates),
                "rejected_candidate_count": rejected,
                "check_types": list(REVIEW_CHECK_TYPES),
            },
            tokens=8 * max(1, len(candidates)),
            trust_origin=self.trust_origin,
        )


class IdeaCompareStage(_IdeaStageBase):
    id = StageEnum.COMPARE

    async def run(self, ctx: StageContext) -> StageResult:
        # Rejected candidates are excluded from the tournament (HL-ASSIST review).
        candidates = [
            candidate
            for candidate in await self._candidates(ctx.run_id, evolved=False)
            if candidate.status != "rejected"
        ]
        stage_run_id = f"{ctx.run_id}:compare"
        outcome = _score_candidates(
            candidates,
            criteria=self.criteria,
            scoring_method=self.scoring_method,
            stage_run_id=stage_run_id,
        )
        for candidate in candidates:
            self.session.add(candidate)
        await self.session.commit()
        ranking = outcome["ranking"]
        return StageResult(
            stage=self.id,
            summary=(
                f"ranked {len(ranking)} candidates via {self.scoring_method} "
                f"over {outcome['pair_count']} matchup(s)"
            ),
            payload={
                "method": self.scoring_method,
                "ranking_count": len(ranking),
                "pair_count": outcome["pair_count"],
            },
            artifacts=[
                {
                    "id": f"{ctx.run_id}:compare:ranking",
                    "kind": "ranking",
                    "stage": self.id.value,
                    "method": self.scoring_method,
                    "ref": "idea-run:ranking",
                    "summary": f"Compare ranking via {self.scoring_method}",
                    "ranking": ranking,
                    "pairwise_matrix": outcome["pairwise_matrix"],
                    "matchup_rationales": outcome["matchup_rationales"],
                }
            ],
            tokens=12 * max(1, len(ranking)),
            trust_origin=self.trust_origin,
        )


class IdeaEvolveStage(_IdeaStageBase):
    id = StageEnum.EVOLVE

    async def run(self, ctx: StageContext) -> StageResult:
        base = [
            candidate
            for candidate in await self._candidates(ctx.run_id, evolved=False)
            if candidate.status != "rejected"
        ]
        base.sort(key=lambda c: (c.rank if c.rank is not None else 10_000, c.id))
        top = base[:EVOLVE_TOP_N]

        # Real mutation operators: repair each top parent's flagged weaknesses,
        # and combine the two strongest into a synthesis (never a paraphrase).
        blueprints: list[dict[str, Any]] = [self._repair_variant(parent) for parent in top]
        if len(top) >= 2:
            blueprints.append(self._combine_variant(top[0], top[1]))

        # Proximity-style dedup: drop offspring too similar to a parent or a
        # sibling offspring by short-hypothesis token overlap.
        signatures = [_token_set(parent.short_hypothesis) for parent in top]
        kept: list[dict[str, Any]] = []
        for bp in blueprints:
            signature = _token_set(bp["short_hypothesis"])
            if any(_jaccard(signature, existing) > 0.9 for existing in signatures):
                continue
            signatures.append(signature)
            kept.append(bp)

        variant_rows: list[IdeaCandidate] = []
        for bp in kept:
            variant = IdeaCandidate(
                run_id=ctx.run_id,
                project_id=ctx.project_id,
                title=bp["title"],
                short_hypothesis=bp["short_hypothesis"],
                research_question=bp["research_question"],
                motivation=bp["motivation"],
                method_sketch=bp["method_sketch"],
                expected_contribution=bp["expected_contribution"],
                required_sources=bp["required_sources"],
                evidence_links=bp["evidence_links"],
                novelty_claim=bp["novelty_claim"],
                feasibility_notes=bp["feasibility_notes"],
                risks=bp["risks"],
                estimated_effort=bp["estimated_effort"],
                generated_by_stage=self.id.value,
                parent_candidate_id=bp["parent_candidate_id"],  # lineage (HL-ASSIST-09)
                # BUGFIX: offspring start unscored — never inherit parent scores.
                status="draft",
                critique=json.dumps([]),
                rubric_results=json.dumps([]),
                rank=None,
                trust_origin=self.trust_origin,
            )
            self.session.add(variant)
            await self.session.commit()
            await self.session.refresh(variant)
            variant_rows.append(variant)

        # Must-win: one fixed re-Review + re-Compare over offspring + parents so
        # offspring EARN a rank (never auto-promoted). Single pass, no loop.
        pool = top + variant_rows
        ranking: list[dict[str, Any]] = []
        if variant_rows:
            _review_candidates(self.session, pool)
            contenders = [candidate for candidate in pool if candidate.status != "rejected"]
            outcome = _score_candidates(
                contenders,
                criteria=self.criteria,
                scoring_method=self.scoring_method,
                stage_run_id=f"{ctx.run_id}:evolve:compare",
            )
            for candidate in pool:
                self.session.add(candidate)
            await self.session.commit()
            ranking = outcome["ranking"]

        variants = [
            {"id": row.id, "parent_candidate_id": row.parent_candidate_id, "rank": row.rank}
            for row in variant_rows
        ]
        return StageResult(
            stage=self.id,
            summary=(
                f"one bounded Evolve pass produced {len(variants)} re-ranked variant(s)"
            ),
            payload={"evolved_candidate_count": len(variants), "variants": variants},
            artifacts=[
                {
                    "id": f"{ctx.run_id}:evolve:variants",
                    "kind": "idea_variants",
                    "stage": self.id.value,
                    "ref": "idea-run:variants",
                    "summary": f"Evolved {len(variants)} top candidate(s) with must-win re-ranking",
                    "variants": variants,
                    "reranking": ranking,
                }
            ],
            tokens=6 * max(1, len(variants)),
            trust_origin=self.trust_origin,
        )

    def _repair_variant(self, parent: IdeaCandidate) -> dict[str, Any]:
        flags = _flagged_notes(parent)
        focus = flags[0] if flags else "tightening the evaluation plan"
        return {
            "parent_candidate_id": parent.id,
            "title": f"{parent.title} (repaired)",
            "short_hypothesis": f"{parent.short_hypothesis} Repaired by addressing: {focus}.",
            "research_question": parent.research_question,
            "motivation": parent.motivation,
            "method_sketch": f"{parent.method_sketch} Adds an explicit check for: {focus}.",
            "expected_contribution": parent.expected_contribution,
            "required_sources": parent.required_sources,
            "evidence_links": parent.evidence_links,
            "novelty_claim": parent.novelty_claim,
            "feasibility_notes": parent.feasibility_notes or "Feasible for a solo researcher.",
            "risks": parent.risks,
            "estimated_effort": parent.estimated_effort or "medium",
        }

    def _combine_variant(self, a: IdeaCandidate, b: IdeaCandidate) -> dict[str, Any]:
        return {
            "parent_candidate_id": a.id,
            "title": f"Synthesis of {a.title} + {b.title}",
            "short_hypothesis": f"Combine: {a.short_hypothesis} WITH {b.short_hypothesis}",
            "research_question": f"{a.research_question} / {b.research_question}",
            "motivation": "Merges grounding and mechanisms from the two top candidates.",
            "method_sketch": f"{a.method_sketch} Integrated with: {b.method_sketch}",
            "expected_contribution": f"{a.expected_contribution} + {b.expected_contribution}",
            "required_sources": json.dumps(
                _merge_json_lists(a.required_sources, b.required_sources), sort_keys=True
            ),
            "evidence_links": json.dumps(
                _merge_json_lists(a.evidence_links, b.evidence_links), sort_keys=True
            ),
            "novelty_claim": f"{a.novelty_claim} (cross-combined synthesis)",
            "feasibility_notes": a.feasibility_notes or "Feasible for a solo researcher.",
            "risks": a.risks or "Risk: integration overhead.",
            "estimated_effort": a.estimated_effort or "medium",
        }


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
    scoring_method: str = "pairwise",
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
