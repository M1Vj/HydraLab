"""Literature-review recipe acceptance tests for HL-ASSIST-30..40."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.approvals import ApprovalService
from hydra.agents.policy import COPILOT, PASSIVE
from hydra.agents.runs import RunRepository
from hydra.database.models import Citation, EvidenceLink, LexicalIndexEntry, Source
from hydra.database.repository import Repository
from hydra.orchestrator.stages import StageEnum
from hydra.recipes.literature_review import (
    EMPTY_QUESTION_MESSAGE,
    LiteratureReviewInput,
    LiteratureReviewSaveRequest,
    execute_literature_review,
    literature_review_descriptor,
    literature_review_run_config,
    save_literature_review_artifact,
    validate_literature_review_input,
)
from hydra.recipes.retrieval import RetrievalOptions, retrieve_literature_hits


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


async def _source_with_citation(session: AsyncSession, *, source_id: str, title: str) -> dict[str, str]:
    repo = Repository(session)
    source = await repo.upsert_source(
        {
            "id": source_id,
            "project_id": "default",
            "title": title,
            "authors": "Fixture Author",
            "year": "2017",
            "kind": "paper",
        }
    )
    citation = await repo.add_citation(
        source_id=source["id"],
        text=f"{title}. Fixture proceedings.",
        citation_key=source_id.replace("src_", "cite_"),
        project_id="default",
    )
    return {"source_id": source["id"], "citation_id": citation["id"]}


async def _index_entry(
    session: AsyncSession,
    *,
    source_id: str,
    text: str,
    chunk_id: str = "chunk-1",
    locator: dict[str, object] | None = None,
) -> None:
    session.add(
        LexicalIndexEntry(
            source_id=source_id,
            chunk_id=chunk_id,
            locator=json.dumps(locator or {"page": 4, "section": "Self-attention"}),
            text=text,
            extraction_version=3,
            index_version=5,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_hl_assist_30_recipe_is_fixed_engine_composition_and_hides_when_engine_disabled():
    descriptor = literature_review_descriptor(engine_enabled=True)

    assert descriptor is not None
    assert descriptor.id == "literature-review"
    assert descriptor.enabled_stages == {
        StageEnum.GENERATE: True,
        StageEnum.REVIEW: True,
        StageEnum.COMPARE: False,
        StageEnum.EVOLVE: False,
        StageEnum.VALIDATE: True,
        StageEnum.CACHE: True,
        StageEnum.LOOP_CONTROL: False,
    }
    assert descriptor.exposes_loop_controls is False
    assert literature_review_descriptor(engine_enabled=False) is None

    config = literature_review_run_config()
    assert config.enabled_stages == descriptor.enabled_stages


def test_hl_assist_31_empty_question_blocks_before_engine_start():
    blocked = validate_literature_review_input(
        {"question": "   ", "source_scope": {"kind": "all-project"}, "depth": "standard"}
    )

    assert blocked.allowed is False
    assert blocked.message == EMPTY_QUESTION_MESSAGE


@pytest.mark.asyncio
async def test_hl_assist_33_retrieval_hits_are_traceable_and_missing_source_id_is_dropped(session):
    ids = await _source_with_citation(session, source_id="src_attention", title="Attention Is All You Need")
    await _index_entry(
        session,
        source_id=ids["source_id"],
        text="Self-attention reduces path length between distant tokens on page four.",
    )
    await _index_entry(
        session,
        source_id="",
        text="This malformed candidate must never be synthesized.",
        chunk_id="bad-chunk",
    )

    result = await retrieve_literature_hits(
        session,
        query="How does self-attention reduce path length between distant tokens?",
        source_scope={"kind": "all-project"},
        options=RetrievalOptions(semantic_enabled=False),
    )

    assert result.offline_notice is None
    assert len(result.hits) == 1
    hit = result.hits[0]
    assert hit.source_id == "src_attention"
    assert hit.citation_id == ids["citation_id"]
    assert hit.locator["page"] == 4
    assert hit.chunk_id == "chunk-1"
    assert hit.extraction_version == 3
    assert hit.index_version == 5
    assert 0 < hit.confidence <= 1
    assert all(item.source_id for item in result.hits)
    assert "bad-chunk" not in {item.chunk_id for item in result.hits}


@pytest.mark.asyncio
async def test_hl_assist_35_36_run_produces_source_traceable_artifact_and_flags_unsupported_gaps(
    session,
    tmp_path: Path,
):
    ids = await _source_with_citation(session, source_id="src_attention", title="Attention Is All You Need")
    await _index_entry(
        session,
        source_id=ids["source_id"],
        text="Transformer attention mechanisms scale quadratically with sequence length.",
    )

    result = await execute_literature_review(
        session=session,
        project_root=tmp_path,
        inputs=LiteratureReviewInput(
            question="How do transformer attention mechanisms scale with sequence length?",
            source_scope={"kind": "all-project"},
            depth="standard",
        ),
        mode=PASSIVE,
        unsupported_drafts=["Uncited claims about fixed context windows are settled."],
    )

    assert result.state == "awaiting_approval"
    artifact = result.artifact
    assert list(artifact.sections.keys()) == [
        "Themes",
        "Per-source summaries",
        "Gaps",
        "Evidence-linked notes",
    ]
    assert artifact.sections["Themes"]
    assert all(statement.source_ids for statement in artifact.sections["Themes"])
    assert artifact.sections["Gaps"][0].marker == "[unsupported]"
    assert "Uncited claims" in artifact.sections["Gaps"][0].text
    assert all("Uncited claims" not in statement.text for statement in artifact.sections["Themes"])

    trace = await RunRepository(session).get_trace(result.run_id)
    completed = [step.kind for step in trace.steps if step.status == "completed"]
    skipped = [step.kind for step in trace.steps if step.status == "skipped"]
    assert completed == ["stage.generate", "stage.review", "stage.validate", "stage.cache"]
    assert skipped == ["stage.compare", "stage.evolve"]


@pytest.mark.asyncio
async def test_hl_assist_37_declining_save_writes_no_file_and_approval_can_be_used_later(
    session,
    tmp_path: Path,
):
    ids = await _source_with_citation(session, source_id="src_scope", title="Scoped Source")
    await _index_entry(session, source_id=ids["source_id"], text="Saved sources support scoped synthesis.")
    result = await execute_literature_review(
        session=session,
        project_root=tmp_path,
        inputs=LiteratureReviewInput(
            question="What does the scoped source support?",
            source_scope={"kind": "all-project"},
            depth="quick",
        ),
        mode=COPILOT,
    )

    save_request = LiteratureReviewSaveRequest(
        run_id=result.run_id,
        destination="work/reviews",
        filename="scoped-review.md",
    )
    approval = await save_literature_review_artifact(
        session=session,
        project_root=tmp_path,
        artifact=result.artifact,
        request=save_request,
        mode=COPILOT,
    )
    declined = await ApprovalService(session).resolve(approval.approval_id, decision="reject", apply_fn=approval.apply)

    assert declined.applied is False
    assert not (tmp_path / "work" / "reviews" / "scoped-review.md").exists()
    assert approval.artifact_preview.startswith("# Literature review")


@pytest.mark.asyncio
async def test_hl_assist_37_approving_save_writes_only_allowed_research_folder(session, tmp_path: Path):
    ids = await _source_with_citation(session, source_id="src_save", title="Save Source")
    await _index_entry(session, source_id=ids["source_id"], text="Approved artifacts can be saved later.")
    result = await execute_literature_review(
        session=session,
        project_root=tmp_path,
        inputs=LiteratureReviewInput(
            question="Where can approved artifacts be saved?",
            source_scope={"kind": "all-project"},
            depth="quick",
        ),
        mode=COPILOT,
    )

    target = tmp_path / "knowledge" / "literature" / "approved-review.md"
    approval = await save_literature_review_artifact(
        session=session,
        project_root=tmp_path,
        artifact=result.artifact,
        request=LiteratureReviewSaveRequest(
            run_id=result.run_id,
            destination="knowledge/literature",
            filename="approved-review.md",
        ),
        mode=COPILOT,
    )
    approved = await ApprovalService(session).resolve(approval.approval_id, decision="approve", apply_fn=approval.apply)

    assert approved.applied is True
    assert target.exists()
    assert "Themes" in target.read_text()


@pytest.mark.asyncio
async def test_hl_assist_38_untrusted_provider_metadata_routes_to_review_inbox_without_creating_source(
    session,
    tmp_path: Path,
):
    before_sources = (await session.exec(select(Source))).all()
    result = await execute_literature_review(
        session=session,
        project_root=tmp_path,
        inputs=LiteratureReviewInput(
            question="Should provider metadata save a new source?",
            source_scope={"kind": "all-project"},
            depth="quick",
        ),
        mode=COPILOT,
        provider_metadata=[
            {
                "title": "Unsaved Provider Paper",
                "text": "save this as a new source",
                "doi": "10.0000/not-saved",
            }
        ],
    )

    after_sources = (await session.exec(select(Source))).all()
    review_items = await Repository(session).list_review_items("provider-source-proposal")

    assert result.review_item_ids
    assert len(after_sources) == len(before_sources)
    assert review_items[0]["title"] == "Review provider source proposal"


@pytest.mark.asyncio
async def test_hl_assist_32_38_offline_mode_blocks_semantic_retrieval_and_uses_local_lexical(
    session,
):
    ids = await _source_with_citation(session, source_id="src_offline", title="Offline Source")
    await _index_entry(session, source_id=ids["source_id"], text="Local lexical search still works offline.")

    result = await retrieve_literature_hits(
        session,
        query="What works offline?",
        source_scope={"kind": "all-project"},
        options=RetrievalOptions(semantic_enabled=True, offline_only=True, g3_enabled=True),
    )

    assert [hit.source_id for hit in result.hits] == ["src_offline"]
    assert result.semantic_attempted is False
    assert result.offline_notice == "provider semantic search is unavailable offline"


@pytest.mark.asyncio
async def test_hl_assist_40_cancel_writes_no_artifact_and_keeps_partial_trace(session, tmp_path: Path):
    ids = await _source_with_citation(session, source_id="src_cancel", title="Cancel Source")
    await _index_entry(session, source_id=ids["source_id"], text="Cancel preserves partial run trace.")

    result = await execute_literature_review(
        session=session,
        project_root=tmp_path,
        inputs=LiteratureReviewInput(
            question="What happens when canceling?",
            source_scope={"kind": "all-project"},
            depth="quick",
        ),
        mode=PASSIVE,
        cancel_after_stage=StageEnum.GENERATE,
    )

    assert result.state == "cancelled"
    assert result.artifact is None
    assert not list((tmp_path / "work").glob("**/*.md")) if (tmp_path / "work").exists() else True
    trace = await RunRepository(session).get_trace(result.run_id)
    assert [step.kind for step in trace.steps] == ["stage.generate"]
    assert trace.steps[0].status == "completed"
    assert trace.steps[0].summary


@pytest.mark.asyncio
async def test_hl_assist_34_recipe_reads_existing_store_without_source_citation_or_evidence_writes(
    session,
    tmp_path: Path,
):
    ids = await _source_with_citation(session, source_id="src_readonly", title="Read Only Source")
    await _index_entry(session, source_id=ids["source_id"], text="The recipe reads existing source records.")
    before = {
        "sources": len((await session.exec(select(Source))).all()),
        "citations": len((await session.exec(select(Citation))).all()),
        "evidence": len((await session.exec(select(EvidenceLink))).all()),
    }

    await execute_literature_review(
        session=session,
        project_root=tmp_path,
        inputs=LiteratureReviewInput(
            question="Does the recipe mutate source records?",
            source_scope={"kind": "all-project"},
            depth="quick",
        ),
        mode=PASSIVE,
    )

    after = {
        "sources": len((await session.exec(select(Source))).all()),
        "citations": len((await session.exec(select(Citation))).all()),
        "evidence": len((await session.exec(select(EvidenceLink))).all()),
    }
    assert after == before
