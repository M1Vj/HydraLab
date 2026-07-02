"""Idea-generation & ranking recipe tests (branch 02-06).

Covers every backend-testable @HL-* scenario from
`.agents/features/02-assistant-co-scientist/06-idea-generation-ranking.md`:
grounding (HL-ASSIST-04), input persistence (HL-ASSIST-02), single staged pass
(HL-ASSIST-03), merged critique (HL-ASSIST-05), normalized rubric
(HL-ASSIST-06/07), Compare-off unranked (HL-ASSIST-08), single Evolve + lineage
(HL-ASSIST-09), toggles without loop controls (HL-ASSIST-10), Review-Inbox-gated
promotion approve/reject (HL-ASSIST-12/HL-MODE-01), untrusted non-promotion
(HL-TRUST-01), offline hard-block (HL-CONSENT-01), and budget/parallelism
block-and-prompt (HL-QUAL-01).
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.runs import RunBudget, RunRepository
from hydra.database.models import AgentRun, IdeaCandidate, Note, ReviewItem, Task
from hydra.database.repository import Repository
from hydra.orchestrator.run import OrchestratorConfigError, RunConfig, RunStateMachine
from hydra.orchestrator.stages import StageEnum
from hydra.recipes.idea_generation import (
    DEFAULT_RUBRIC_CRITERIA,
    DEFAULT_STAGE_TOGGLES,
    IDEA_RECIPE_ID,
    REVIEW_CHECK_TYPES,
    IdeaCompareStage,
    IdeaEvolveStage,
    IdeaGenerateStage,
    IdeaPromotionService,
    IdeaReviewStage,
    IdeaRunInput,
    _load_grounding,
    resolve_parallelism,
    resolve_slash_command,
    run_idea_recipe,
    unresolved_evidence_links,
)
from hydra.database.models import LexicalIndexEntry


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine):
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session


async def _seed_sources(session: AsyncSession, *, project_id="default", trust_origin="user") -> list[str]:
    repo = Repository(session)
    ids: list[str] = []
    for i in range(3):
        src = await repo.upsert_source(
            {
                "id": f"src-{i}",
                "project_id": project_id,
                "title": f"Efficient attention paper {i}",
                "trust_origin": trust_origin,
            }
        )
        ids.append(src["id"])
    # one evidence record so an evidence_id can attach to a grounded ref
    claim = await repo.add_claim(text="Sub-quadratic attention scales", project_id=project_id)
    await repo.add_evidence(
        claim_id=claim["id"],
        source_id=ids[0],
        passage="Linear attention approximates softmax.",
        support="supports",
        confidence=0.9,
    )
    return ids


def _input() -> IdeaRunInput:
    return IdeaRunInput(
        topic="sub-quadratic attention for long documents",
        source_scope="Transformer Survey 2024 working set",
        constraints="solo researcher, no GPU cluster",
        novelty_target="high",
    )


# --- HL-ASSIST-01 -----------------------------------------------------------


def test_hl_assist_01_slash_commands_resolve_to_builtin_recipe():
    assert resolve_slash_command("/generate-hypotheses") == IDEA_RECIPE_ID
    assert resolve_slash_command("rank-ideas") == IDEA_RECIPE_ID
    with pytest.raises(KeyError):
        resolve_slash_command("/not-a-recipe")


@pytest.mark.asyncio
async def test_hl_assist_01_run_is_a_single_orchestrated_recipe(session):
    await _seed_sources(session)
    result = await run_idea_recipe(session, run_input=_input())
    run = await session.get(AgentRun, result.run_id)
    assert run.recipe == IDEA_RECIPE_ID  # routed through the orchestrator recipe, not a raw agent
    trace = await RunRepository(session).get_trace(result.run_id)
    kinds = [step.kind for step in trace.steps]
    assert "stage.generate" in kinds and "stage.compare" in kinds
    assert not any("raw_agent" in k for k in kinds)


# --- HL-ASSIST-02 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_hl_assist_02_persists_input_schema_with_run(session):
    await _seed_sources(session)
    result = await run_idea_recipe(session, run_input=_input())
    run = await session.get(AgentRun, result.run_id)
    saved = json.loads(run.inputs_ref)[0]
    assert saved == {
        "topic": "sub-quadratic attention for long documents",
        "source_scope": "Transformer Survey 2024 working set",
        "constraints": "solo researcher, no GPU cluster",
        "novelty_target": "high",
    }


# --- HL-ASSIST-04 (grounding, candidate round-trip) -------------------------


@pytest.mark.asyncio
async def test_hl_assist_04_candidate_roundtrips_and_grounds_in_saved_sources(session):
    seeded = set(await _seed_sources(session))
    result = await run_idea_recipe(session, run_input=_input())
    candidates = (
        await session.exec(select(IdeaCandidate).where(IdeaCandidate.run_id == result.run_id))
    ).all()
    assert candidates
    for candidate in candidates:
        # every candidate-schema field round-trips
        for field_name in (
            "title",
            "short_hypothesis",
            "research_question",
            "motivation",
            "method_sketch",
            "expected_contribution",
            "novelty_claim",
            "feasibility_notes",
            "risks",
            "estimated_effort",
            "generated_by_stage",
            "status",
        ):
            assert getattr(candidate, field_name)
        # every evidence link resolves to a saved source; none fabricated
        assert await unresolved_evidence_links(session, candidate) == []
        for link in json.loads(candidate.evidence_links):
            assert link["source_id"] in seeded


# --- HL-ASSIST-03 (single staged pass, stops) -------------------------------


@pytest.mark.asyncio
async def test_hl_assist_03_runs_staged_pass_once_and_stops(session):
    await _seed_sources(session)
    result = await run_idea_recipe(
        session,
        run_input=_input(),
        stage_toggles={"generate": True, "review": True, "compare": True, "evolve": True},
    )
    assert result.state == "completed"
    trace = await RunRepository(session).get_trace(result.run_id)
    ran = [s.kind for s in trace.steps if s.status == "completed"]
    assert ran.count("stage.generate") == 1
    assert ran.count("stage.review") == 1
    assert ran.count("stage.compare") == 1
    assert ran.count("stage.evolve") == 1


# --- HL-ASSIST-05 (typed reflection checks per candidate) -------------------


@pytest.mark.asyncio
async def test_hl_assist_05_review_attaches_typed_checks_per_candidate(session):
    await _seed_sources(session)
    result = await run_idea_recipe(session, run_input=_input())
    candidates = (
        await session.exec(
            select(IdeaCandidate).where(IdeaCandidate.run_id == result.run_id)
        )
    ).all()
    for candidate in candidates:
        critique = json.loads(candidate.critique)
        # Critique is now a LIST of typed check records, not a merged dict.
        assert isinstance(critique, list) and critique
        assert {record["check_type"] for record in critique} == set(REVIEW_CHECK_TYPES)
        for record in critique:
            assert record["verdict"] in {"pass", "flag", "reject"}
            assert isinstance(record["evidence_refs"], list)
            assert record["notes"]
        # Well-grounded candidates are never rejected.
        assert candidate.status != "rejected"
        assert all(record["verdict"] != "reject" for record in critique)


# --- HL-ASSIST-06 / 07 (normalized rubric) ----------------------------------


@pytest.mark.asyncio
async def test_hl_assist_06_07_compare_produces_normalized_rubric_scores(session):
    await _seed_sources(session)
    result = await run_idea_recipe(session, run_input=_input())
    candidates = (
        await session.exec(select(IdeaCandidate).where(IdeaCandidate.run_id == result.run_id))
    ).all()
    ranks = sorted(c.rank for c in candidates)
    assert ranks == list(range(1, len(candidates) + 1))  # a total ranked order
    for candidate in candidates:
        results = json.loads(candidate.rubric_results)
        assert {r["criterion"] for r in results} == set(DEFAULT_RUBRIC_CRITERIA)
        for record in results:
            assert isinstance(record["value"], (int, float))
            assert record["rationale"]
            assert record["stage_run_id"] == f"{result.run_id}:compare"
            assert isinstance(record["source_refs"], list)


# --- HL-ASSIST-08 (Compare off -> unranked, no scores) ----------------------


@pytest.mark.asyncio
async def test_hl_assist_08_compare_off_yields_unranked_candidates_without_scores(session):
    await _seed_sources(session)
    result = await run_idea_recipe(
        session,
        run_input=_input(),
        stage_toggles={"generate": True, "review": True, "compare": False, "evolve": False},
    )
    candidates = (
        await session.exec(select(IdeaCandidate).where(IdeaCandidate.run_id == result.run_id))
    ).all()
    assert candidates
    for candidate in candidates:
        assert json.loads(candidate.rubric_results) == []
        assert candidate.rank is None
        assert candidate.status == "reviewed"


# --- HL-ASSIST-09 (single Evolve + lineage) ---------------------------------


@pytest.mark.asyncio
async def test_hl_assist_09_single_evolve_pass_records_parent_lineage(session):
    await _seed_sources(session)
    result = await run_idea_recipe(
        session,
        run_input=_input(),
        stage_toggles={"generate": True, "review": True, "compare": True, "evolve": True},
    )
    candidates = (
        await session.exec(select(IdeaCandidate).where(IdeaCandidate.run_id == result.run_id))
    ).all()
    variants = [c for c in candidates if c.generated_by_stage == "evolve"]
    assert variants
    base_ids = {c.id for c in candidates if c.generated_by_stage == "generate"}
    for variant in variants:
        assert variant.parent_candidate_id in base_ids

    trace = await RunRepository(session).get_trace(result.run_id)
    assert [s.kind for s in trace.steps if s.status == "completed"].count("stage.evolve") == 1


@pytest.mark.asyncio
async def test_hl_assist_09_evolve_off_creates_no_variants(session):
    await _seed_sources(session)
    result = await run_idea_recipe(session, run_input=_input())  # evolve OFF by default
    candidates = (
        await session.exec(select(IdeaCandidate).where(IdeaCandidate.run_id == result.run_id))
    ).all()
    assert [c for c in candidates if c.generated_by_stage == "evolve"] == []


# --- HL-ASSIST-10 (toggles, no loop controls) -------------------------------


def test_hl_assist_10_default_toggles_have_no_loop_or_population_controls():
    assert DEFAULT_STAGE_TOGGLES["generate"] is True
    assert DEFAULT_STAGE_TOGGLES["review"] is True
    keys = set(DEFAULT_STAGE_TOGGLES)
    assert keys == {"generate", "review", "compare", "evolve"}
    assert not any(k in keys for k in ("loop_count", "population_size", "stop_condition"))
    with pytest.raises(OrchestratorConfigError):
        RunConfig.resolve(loop_count=2)


# --- HL-ASSIST-12 / HL-MODE-01 (Review-Inbox-gated promotion) ---------------


@pytest.mark.asyncio
async def test_hl_assist_12_promote_to_task_requires_review_inbox_approval(session):
    await _seed_sources(session)
    result = await run_idea_recipe(session, run_input=_input())
    candidate = (
        await session.exec(select(IdeaCandidate).where(IdeaCandidate.run_id == result.run_id))
    ).first()

    service = IdeaPromotionService(session)
    proposal = await service.propose(candidate_id=candidate.id, target_kind="task")
    assert proposal["status"] == "review_inbox"

    # No task exists in the workspace until the researcher approves the item.
    assert (await session.exec(select(Task))).all() == []
    review = await session.get(ReviewItem, proposal["review_item_id"])
    assert review.item_type == "idea-promotion" and review.status == "pending"

    approved = await service.approve(proposal["review_item_id"])
    tasks = (await session.exec(select(Task))).all()
    assert len(tasks) == 1
    carried = json.loads(tasks[0].detail)
    assert carried["candidate_id"] == candidate.id
    assert carried["rubric_results"]  # rubric scores carried
    assert carried["rationale"]
    assert carried["evidence_links"]
    assert approved["created_target_id"] == tasks[0].id
    refreshed = await session.get(IdeaCandidate, candidate.id)
    assert refreshed.status == "promoted"


@pytest.mark.asyncio
async def test_hl_assist_12_rejecting_promotion_creates_no_artifact(session):
    await _seed_sources(session)
    result = await run_idea_recipe(session, run_input=_input())
    candidate = (
        await session.exec(select(IdeaCandidate).where(IdeaCandidate.run_id == result.run_id))
    ).first()

    service = IdeaPromotionService(session)
    proposal = await service.propose(candidate_id=candidate.id, target_kind="note")
    rejected = await service.reject(proposal["review_item_id"])

    assert rejected["created_target_id"] is None
    assert (await session.exec(select(Note))).all() == []
    assert (await session.exec(select(Task))).all() == []
    review = await session.get(ReviewItem, proposal["review_item_id"])
    assert review.status == "rejected"
    refreshed = await session.get(IdeaCandidate, candidate.id)
    assert refreshed.status == "ranked"  # remains on the board, unchanged


# --- HL-TRUST-01 (untrusted text cannot auto-promote) -----------------------


@pytest.mark.asyncio
async def test_hl_trust_01_untrusted_source_text_never_auto_promotes(session):
    await _seed_sources(session, trust_origin="untrusted-external")
    # The recipe reads untrusted source text during generation.
    result = await run_idea_recipe(session, run_input=_input(), trust_origin="untrusted-external")

    # No task/note is created automatically by the run itself.
    assert (await session.exec(select(Task))).all() == []
    assert (await session.exec(select(Note))).all() == []

    # Any resulting proposal appears in the Review Inbox for explicit approval.
    candidate = (
        await session.exec(select(IdeaCandidate).where(IdeaCandidate.run_id == result.run_id))
    ).first()
    assert candidate.trust_origin == "untrusted-external"
    proposal = await IdeaPromotionService(session).propose(
        candidate_id=candidate.id, target_kind="task", mode="full_access"
    )
    assert proposal["status"] == "review_inbox"
    assert (await session.exec(select(Task))).all() == []  # still nothing auto-created


# --- HL-CONSENT-01 (offline hard-block) -------------------------------------


@pytest.mark.asyncio
async def test_hl_consent_01_offline_only_hard_blocks_before_any_provider_send(session):
    await _seed_sources(session)
    result = await run_idea_recipe(session, run_input=_input(), offline_only=True)

    assert result.state == "permission-denied"
    # No candidates were produced (the run stopped before any stage ran).
    assert (await session.exec(select(IdeaCandidate))).all() == []
    run = await session.get(AgentRun, result.run_id)
    assert run.status == "blocked"
    trace = await RunRepository(session).get_trace(result.run_id)
    assert trace.steps[-1].kind == "consent.offline_blocked"
    assert trace.steps[-1].payload["state"] == "permission-denied"


# --- HL-QUAL-01 (budget + parallelism block-and-prompt) ---------------------


@pytest.mark.asyncio
async def test_hl_qual_01_budget_ceiling_pauses_and_prompts(session):
    await _seed_sources(session)
    result = await run_idea_recipe(
        session,
        run_input=_input(),
        budget=RunBudget(run_budget_tokens=1, wall_clock_seconds=120),
    )
    assert result.state == "budget_blocked"
    run = await session.get(AgentRun, result.run_id)
    assert run.status == "blocked"
    trace = await RunRepository(session).get_trace(result.run_id)
    assert trace.steps[-1].kind == "budget.blocked"
    assert "continue" in trace.steps[-1].summary


def test_hl_qual_01_parallelism_blocks_and_prompts_at_two_concurrent_calls():
    assert resolve_parallelism(2)["state"] == "proceed"
    blocked = resolve_parallelism(3)
    assert blocked["state"] == "blocked"
    assert "continue" in blocked["reason"] and "stop" in blocked["reason"]


# --- HL-ASSIST-13 (mid-run failure keeps completed-stage prefix) ------------


@pytest.mark.asyncio
async def test_hl_assist_13_provider_error_mid_run_keeps_completed_stage_prefix(session):
    seeded = await _seed_sources(session)
    grounding = await _load_grounding(session, "default")
    common = dict(
        session=session,
        run_input=_input(),
        grounding=grounding,
        candidate_count=3,
        criteria=DEFAULT_RUBRIC_CRITERIA,
        scoring_method="rubric",
        trust_origin="user",
    )

    class FailingCompare(IdeaCompareStage):
        async def run(self, ctx):
            raise RuntimeError("provider error during Compare")

    config = RunConfig.resolve(
        stage_overrides={"generate": True, "review": True, "compare": True}
    )
    machine = RunStateMachine(
        RunRepository(session),
        config,
        stages={
            StageEnum.GENERATE: IdeaGenerateStage(**common),
            StageEnum.REVIEW: IdeaReviewStage(**common),
            StageEnum.COMPARE: FailingCompare(**common),
        },
    )
    run = await RunRepository(session).create_run(project_id="default", mode="passive", recipe=IDEA_RECIPE_ID)
    execution = await machine.resume(run_id=run.id, project_id="default", mode="passive")

    assert execution.state == "failed"
    trace = await RunRepository(session).get_trace(run.id)
    completed = [s.kind for s in trace.steps if s.status == "completed"]
    assert completed == ["stage.generate", "stage.review"]  # completed prefix preserved
    # generated + reviewed candidates remain visible
    assert seeded
    candidates = (await session.exec(select(IdeaCandidate).where(IdeaCandidate.run_id == run.id))).all()
    assert candidates and all(c.status == "reviewed" for c in candidates)


# --- Faithfulness enhancements ----------------------------------------------


async def _ranking_artifact(session, run_id: str) -> dict:
    run = await session.get(AgentRun, run_id)
    for artifact in json.loads(run.artifacts or "[]"):
        if artifact.get("kind") == "ranking":
            return artifact
    raise AssertionError("no ranking artifact persisted")


# Enhancement 1: Compare -> real pairwise tournament + BTL matrix.
@pytest.mark.asyncio
async def test_compare_emits_pairwise_matrix_and_btl_ranking(session):
    await _seed_sources(session)
    result = await run_idea_recipe(session, run_input=_input())  # default is now "pairwise"
    candidates = (
        await session.exec(select(IdeaCandidate).where(IdeaCandidate.run_id == result.run_id))
    ).all()
    ids = {c.id for c in candidates}
    n = len(candidates)
    expected_pairs = n * (n - 1) // 2

    artifact = await _ranking_artifact(session, result.run_id)
    assert artifact["method"] == "pairwise"
    matrix = artifact["pairwise_matrix"]
    assert set(matrix) == set(DEFAULT_RUBRIC_CRITERIA)
    for criterion, cell in matrix.items():
        # Every pair yields exactly one winner per criterion.
        assert sum(cell["wins"].values()) == expected_pairs
    rationales = artifact["matchup_rationales"]
    assert rationales and all(r["winner"] in ids for r in rationales)
    assert len(rationales) == expected_pairs * len(DEFAULT_RUBRIC_CRITERIA)

    # Ranking is a total order; #1 has the highest aggregate BTL strength.
    ranking = artifact["ranking"]
    assert [row["rank"] for row in ranking] == list(range(1, n + 1))
    assert ranking[0]["score"] >= ranking[-1]["score"]

    # RubricResults carry normalized [0,1] BTL strengths with pairwise rationale.
    for candidate in candidates:
        for record in json.loads(candidate.rubric_results):
            assert 0.0 <= record["value"] <= 1.0
            assert "pairwise" in record["rationale"]
            assert record["stage_run_id"] == f"{result.run_id}:compare"


# Enhancement 2a: Evolve offspring earn scores (never inherit parent scores).
@pytest.mark.asyncio
async def test_evolve_variants_earn_scores_and_are_not_copied(session):
    await _seed_sources(session)
    result = await run_idea_recipe(
        session,
        run_input=_input(),
        stage_toggles={"generate": True, "review": True, "compare": True, "evolve": True},
    )
    candidates = (
        await session.exec(select(IdeaCandidate).where(IdeaCandidate.run_id == result.run_id))
    ).all()
    variants = [c for c in candidates if c.generated_by_stage == "evolve"]
    assert variants
    for variant in variants:
        results = json.loads(variant.rubric_results)
        assert results  # offspring earned their own scores
        # Earned in the Evolve re-ranking pass, NOT copied from the parent's
        # main Compare pass (whose stage_run_id ends in ":compare").
        assert all(r["stage_run_id"] == f"{result.run_id}:evolve:compare" for r in results)
        assert variant.rank is not None
        assert variant.status == "ranked"


# Enhancement 2b: Evolve dedups near-identical offspring (Proximity-style).
@pytest.mark.asyncio
async def test_evolve_dedups_near_identical_offspring(session):
    ids = await _seed_sources(session)
    run = await RunRepository(session).create_run(project_id="default", mode="passive", recipe=IDEA_RECIPE_ID)
    links = json.dumps([{"source_id": ids[0], "kind": "source"}], sort_keys=True)
    parents = []
    for rank in (1, 2):
        parent = IdeaCandidate(
            run_id=run.id,
            project_id="default",
            title=f"Parent {rank}",
            short_hypothesis="Identical hypothesis about attention scaling.",
            research_question="How does attention scale?",
            motivation="grounded",
            method_sketch="staged method",
            expected_contribution="contribution",
            required_sources=json.dumps([ids[0]], sort_keys=True),
            evidence_links=links,
            novelty_claim="novel",
            feasibility_notes="feasible",
            risks="risk",
            estimated_effort="medium",
            generated_by_stage="generate",
            status="ranked",
            critique=json.dumps([]),
            rank=rank,
        )
        session.add(parent)
        await session.commit()
        await session.refresh(parent)
        parents.append(parent)

    grounding = await _load_grounding(session, "default")
    common = dict(
        session=session,
        run_input=_input(),
        grounding=grounding,
        candidate_count=5,
        criteria=DEFAULT_RUBRIC_CRITERIA,
        scoring_method="pairwise",
        trust_origin="user",
    )
    from hydra.orchestrator.stages import StageContext
    ctx = StageContext(run_id=run.id, project_id="default", mode="passive", data={}, config=None)
    await IdeaEvolveStage(**common).run(ctx)

    variants = (
        await session.exec(
            select(IdeaCandidate).where(
                IdeaCandidate.run_id == run.id, IdeaCandidate.generated_by_stage == "evolve"
            )
        )
    ).all()
    # Two identical parents would yield two identical repair variants; dedup keeps
    # one repair + the (distinct) combine variant.
    assert len(variants) == 2
    hypotheses = [v.short_hypothesis for v in variants]
    assert len(set(hypotheses)) == len(hypotheses)


# Enhancement 3: Review reject verdict excludes the candidate from Compare.
@pytest.mark.asyncio
async def test_review_reject_excludes_candidate_from_compare(session):
    ids = await _seed_sources(session)
    run = await RunRepository(session).create_run(project_id="default", mode="passive", recipe=IDEA_RECIPE_ID)

    def _candidate(title, links):
        return IdeaCandidate(
            run_id=run.id,
            project_id="default",
            title=title,
            short_hypothesis=f"{title} hypothesis under constraints.",
            research_question="How?",
            motivation="grounded",
            method_sketch="staged method",
            expected_contribution="contribution",
            required_sources=json.dumps([], sort_keys=True),
            evidence_links=links,
            novelty_claim="novel",
            feasibility_notes="feasible",
            risks="risk",
            estimated_effort="medium",
            generated_by_stage="generate",
            status="draft",
        )

    grounded = _candidate("Grounded", json.dumps([{"source_id": ids[0], "kind": "source"}], sort_keys=True))
    ungrounded = _candidate("Ungrounded", json.dumps([], sort_keys=True))
    session.add(grounded)
    session.add(ungrounded)
    await session.commit()
    await session.refresh(grounded)
    await session.refresh(ungrounded)

    grounding = await _load_grounding(session, "default")
    common = dict(
        session=session,
        run_input=_input(),
        grounding=grounding,
        candidate_count=2,
        criteria=DEFAULT_RUBRIC_CRITERIA,
        scoring_method="pairwise",
        trust_origin="user",
    )
    from hydra.orchestrator.stages import StageContext
    ctx = StageContext(run_id=run.id, project_id="default", mode="passive", data={}, config=None)
    await IdeaReviewStage(**common).run(ctx)

    refreshed_ungrounded = await session.get(IdeaCandidate, ungrounded.id)
    assert refreshed_ungrounded.status == "rejected"
    critique = json.loads(refreshed_ungrounded.critique)
    assert any(r["check_type"] == "novelty_grounding" and r["verdict"] == "reject" for r in critique)

    compare_result = await IdeaCompareStage(**common).run(ctx)
    ranked_ids = {row["id"] for row in compare_result.artifacts[0]["ranking"]}
    assert grounded.id in ranked_ids
    assert ungrounded.id not in ranked_ids  # rejected candidate excluded
    refreshed_ungrounded = await session.get(IdeaCandidate, ungrounded.id)
    assert refreshed_ungrounded.rank is None
    assert json.loads(refreshed_ungrounded.rubric_results) == []


# Enhancement 4: Generate assigns sources by retrieval relevance, not round-robin.
@pytest.mark.asyncio
async def test_generate_grounds_in_retrieval_relevant_source(session):
    ids = await _seed_sources(session)
    relevant = ids[1]
    # Only the relevant source has an indexed chunk matching the topic terms, so
    # retrieval returns it alone and every candidate must ground in it.
    session.add(
        LexicalIndexEntry(
            source_id=relevant,
            chunk_id="chunk-rel",
            locator=json.dumps({"page": 1}),
            text="Sub-quadratic attention scales to long documents efficiently.",
            extraction_version=1,
            index_version=1,
        )
    )
    await session.commit()

    result = await run_idea_recipe(
        session,
        run_input=_input(),
        stage_toggles={"generate": True, "review": False, "compare": False, "evolve": False},
    )
    candidates = (
        await session.exec(select(IdeaCandidate).where(IdeaCandidate.run_id == result.run_id))
    ).all()
    assert candidates
    for candidate in candidates:
        source_ids = {link["source_id"] for link in json.loads(candidate.evidence_links)}
        assert source_ids == {relevant}
        # And retrieval chunk provenance is carried on the link.
        assert all(link.get("chunk_id") == "chunk-rel" for link in json.loads(candidate.evidence_links))
