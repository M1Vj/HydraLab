import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import Source, Task
from hydra.database.repository import Repository


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        yield db
    await engine.dispose()


async def _create_project_content(repo: Repository, project_id: str) -> dict[str, dict]:
    source = await repo.upsert_source(
        {
            "id": f"src-{project_id}",
            "title": f"{project_id} source",
            "project_id": project_id,
        }
    )
    note = await repo.add_note(
        f"{project_id} note",
        f"body for {project_id}",
        source_id=source["id"],
        project_id=project_id,
    )
    citation = await repo.add_citation(
        source_id=source["id"],
        text=f"{project_id} citation",
        project_id=project_id,
    )
    claim = await repo.add_claim(
        text=f"{project_id} claim",
        project_id=project_id,
    )
    evidence = await repo.add_evidence(
        claim_id=claim["id"],
        source_id=source["id"],
        citation_id=citation["id"],
        passage=f"{project_id} passage",
        support="supported",
        confidence=0.9,
    )
    return {
        "source": source,
        "note": note,
        "citation": citation,
        "claim": claim,
        "evidence": evidence,
    }


@pytest.mark.asyncio
async def test_project_scoped_reads_only_return_rows_for_that_project(session):
    repo = Repository(session)
    alpha = await _create_project_content(repo, "alpha")
    beta = await _create_project_content(repo, "beta")

    assert [row["id"] for row in await repo.list_sources(project_id="alpha")] == [alpha["source"]["id"]]
    assert [row["id"] for row in await repo.list_sources(project_id="beta")] == [beta["source"]["id"]]
    assert [row["id"] for row in await repo.list_citations(project_id="alpha")] == [alpha["citation"]["id"]]
    assert [row["id"] for row in await repo.list_claims(project_id="beta")] == [beta["claim"]["id"]]
    assert [row["id"] for row in await repo.search_notes(project_id="alpha")] == [alpha["note"]["id"]]
    assert [row["id"] for row in await repo.list_evidence(project_id="beta")] == [beta["evidence"]["id"]]


@pytest.mark.asyncio
async def test_legacy_null_project_rows_map_to_default_scope_only(session):
    repo = Repository(session)
    session.add(Source(id="src-legacy", title="legacy source", project_id=None))
    await session.commit()

    assert [row["id"] for row in await repo.list_sources(project_id="default")] == ["src-legacy"]
    assert await repo.list_sources(project_id="alpha") == []


@pytest.mark.asyncio
async def test_unscoped_reads_still_return_all_project_rows(session):
    repo = Repository(session)
    await _create_project_content(repo, "alpha")
    await _create_project_content(repo, "beta")
    session.add(Source(id="src-legacy", title="legacy source", project_id=None))
    await session.commit()

    assert {row["id"] for row in await repo.list_sources()} == {"src-alpha", "src-beta", "src-legacy"}


@pytest.mark.asyncio
async def test_merge_sources_refuses_cross_project(session):
    repo = Repository(session)
    await repo.upsert_source({"id": "src-a", "title": "A", "doi": "10.1/x", "project_id": "alpha"})
    await repo.upsert_source({"id": "src-b", "title": "B", "doi": "10.1/x", "project_id": "beta"})

    with pytest.raises(ValueError, match="different projects"):
        await repo.merge_sources(["src-a", "src-b"], reason="exact_identifier")

    # Same-project merge still works.
    await repo.upsert_source({"id": "src-c", "title": "A dup", "doi": "10.1/x", "project_id": "alpha"})
    result = await repo.merge_sources(["src-a", "src-c"], reason="exact_identifier")
    assert result["survivor_id"] in {"src-a", "src-c"}


@pytest.mark.asyncio
async def test_list_sources_excludes_trashed_by_default(session):
    repo = Repository(session)
    live = await repo.upsert_source({"id": "src-live", "title": "Live", "project_id": "default"})
    trashed = await repo.upsert_source({"id": "src-trashed", "title": "Trashed", "project_id": "default"})
    await repo.trash_source(trashed["id"], confirmed=True)

    default_ids = [row["id"] for row in await repo.list_sources(project_id="default")]
    assert default_ids == [live["id"]]

    with_trashed = {row["id"] for row in await repo.list_sources(project_id="default", include_trashed=True)}
    assert with_trashed == {live["id"], trashed["id"]}


@pytest.mark.asyncio
async def test_detect_duplicates_never_pairs_across_projects(session):
    repo = Repository(session)
    await repo.upsert_source({"id": "dup-alpha", "title": "Attention", "doi": "10.1/same", "project_id": "alpha"})
    await repo.upsert_source({"id": "dup-beta", "title": "Attention", "doi": "10.1/same", "project_id": "beta"})

    # Unscoped scan must not pair the identical-DOI sources across projects, and
    # must not queue a merge proposal that would breach isolation / dead-end.
    verdicts = await repo.detect_duplicates()
    pairs = {frozenset((v["left_id"], v["right_id"])) for v in verdicts}
    assert frozenset(("dup-alpha", "dup-beta")) not in pairs
    assert await repo.list_review_items(item_type="duplicate-merge-proposal") == []

    # Same-project duplicates are still detected.
    await repo.upsert_source({"id": "dup-alpha2", "title": "Attention", "doi": "10.1/same", "project_id": "alpha"})
    scoped = await repo.detect_duplicates(project_id="alpha")
    scoped_pairs = {frozenset((v["left_id"], v["right_id"])) for v in scoped}
    assert frozenset(("dup-alpha", "dup-alpha2")) in scoped_pairs


@pytest.mark.asyncio
async def test_legacy_task_column_label_is_normalized_on_read(session):
    # A pre-fix DB may hold a display label ("To Do") in column_name; the board
    # only renders the four canonical ids, so an un-normalized label would orphan
    # the task. Read-time normalization repairs it without a migration.
    repo = Repository(session)
    session.add(Task(id="task-legacy", title="Legacy", column_name="To Do", project_id="default"))
    session.add(Task(id="task-bogus", title="Bogus", column_name="whatever", project_id="default"))
    await session.commit()

    tasks = {t["id"]: t for t in await repo.list_tasks(project_id="default")}
    assert tasks["task-legacy"]["column"] == "to_do"
    assert tasks["task-legacy"]["status"] == "to_do"
    # An unrecognizable value falls back to the first column rather than vanishing.
    assert tasks["task-bogus"]["column"] == "to_do"


@pytest.mark.asyncio
async def test_add_note_without_project_id_is_written_to_default_project(session):
    repo = Repository(session)
    note = await repo.add_note("default note", "default body")

    default_notes = await repo.search_notes(project_id="default")

    assert [row["id"] for row in default_notes] == [note["id"]]
    assert default_notes[0]["project_id"] == "default"
