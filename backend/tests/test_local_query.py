"""Offline query syntax, literal matching and real retrieval boundary tests."""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.app import create_app
from hydra.database.models import LexicalIndexEntry, Source
from hydra.database.repository import Repository
from hydra.recipes.idea_generation import DEFAULT_RUBRIC_CRITERIA, IdeaGenerateStage, IdeaRunInput, _load_grounding
from hydra.recipes.query import MAX_QUERY_CLAUSES, MAX_QUERY_LENGTH, QuerySyntaxError, compile_local_query, compile_plain_query
from hydra.recipes.retrieval import RetrievalOptions, retrieve_literature_hits


@pytest.mark.parametrize("query,text,expected", [
    ('"neural network"', "A Neural Network improves recall.", 1.0),
    ('"neural network"', "A neural deep network.", 0.0),
    ('"neural network"', "neural networks", 0.0),
    ('"neural network"', "neural\n\t network", 1.0),
    ('"neural network" "recall"', "neural network recall", 1.0),
    ('"neural network" "recall"', "neural network precision", 0.0),
    ('"neural network" transformer', "neural network", 0.5),
    ('"neural network" transformer', "transformer only", 0.0),
    ('retrieval -survey', "retrieval survey", 0.0),
    ('retrieval -survey', "retrieval surveys", 1.0),
    ('retrieval -"case study"', "retrieval CASE\nSTUDY", 0.0),
    ('retrieval -"case study"', "retrieval study case", 1.0),
    ('"AI" -survey', "AI methods", 1.0),
    ('"AI"', "said", 0.0),
    ('"naïve café"', "NAÏVE CAFÉ results", 1.0),
    ('"Straße"', "STRASSE", 1.0),
    ('"a+b"', "a+b", 1.0),
    ('"a+b"', "aaab", 0.0),
    ('"[x]"', "[x]", 1.0),
    ('"[x]"', "x", 0.0),
    ('"C++"', "C++", 1.0),
    ('"C++"', "ABC++", 0.0),
    ('"a\\\"b"', 'a"b', 1.0),
    ('"path\\\\name"', 'path\\name', 1.0),
    ('"research" -peer-reviewed', "research peer-reviewed", 0.0),
    ('"research" -peer-reviewed', "research peer review", 1.0),
    ('"foo" "foo" bar', "foo", 0.5),
    ('retrieval -"drop table"', "retrieval; DROP TABLE", 0.0),
    ('"a a"', 'ba a a', 1.0),
    ('retrieval -"a a"', 'retrieval ba a a', 0.0),
    ('"x-x"', 'ax-x-x', 1.0),
    ('retrieval -"x-x"', 'retrieval ax-x-x', 0.0),
    ('"café"', "cafe\u0301", 1.0),
    ('"cafe"', "cafe\u0301", 0.0),
    ('"i"', "İx", 0.0),
    ('"q"', "q\u0301", 0.0),
    ('"q\u0301"', "q\u0301", 1.0),
])
def test_query_filters_are_literal(query, text, expected):
    assert compile_local_query(query).confidence(text) == expected


@pytest.mark.parametrize("query", [
    '"unfinished', 'retrieval -"unfinished', '""', '"   "',
    'retrieval -""', '"phrase"tail', 'prefix"phrase"', '"one""two"',
    '-survey', '-"case study"', 'AI -survey',
    'x' * (MAX_QUERY_LENGTH + 1), 'term ' * (MAX_QUERY_CLAUSES + 1),
])
def test_invalid_query_fails_closed(query):
    with pytest.raises(QuerySyntaxError):
        compile_local_query(query)


def test_plain_queries_preserve_previous_ranking():
    queries = ["", "   ", "AI", "data", "state-of-the-art", "retrieval retrieval", "café", "methods and recall", "-", "x.y*?["]
    texts = ["", " ", "database method", "Retrieval and recall", "State of the art research", "café x.y"]
    for query in queries:
        terms = {term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) > 2}
        for text in texts:
            matched = sum(term in text.lower() for term in terms)
            expected = (min(1.0, max(0.05, matched / len(terms))) if matched else 0.0) if terms else (0.25 if text.strip() else 0.0)
            assert compile_local_query(query).confidence(text) == expected


@pytest.mark.asyncio
async def test_invalid_query_does_not_read_database():
    class UnavailableSession:
        def __getattr__(self, name):
            raise AssertionError(f"Unexpected database access: {name}")

    result = await retrieve_literature_hits(UnavailableSession(), query='-survey', source_scope={}, options=RetrievalOptions(query_filters=True))
    assert result.hits == []
    assert result.semantic_attempted is False
    assert result.notices == ["Invalid local search query: Add a positive search term or quoted phrase before excluding text."]


@pytest.mark.asyncio
async def test_filtered_retrieval_keeps_scope_locators_citations_and_offline_gate():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            repo = Repository(session)
            texts = {
                "keep": "A neural network improves recall.",
                "exclude": "A neural network survey.",
                "loose": "Neural methods for network recall.",
                "other": "A neural network improves recall.",
                "trashed": "A neural network improves recall.",
            }
            for source_id, text in texts.items():
                session.add(Source(id=source_id, title=source_id, project_id="other" if source_id == "other" else "default", trashed=source_id == "trashed"))
                session.add(LexicalIndexEntry(source_id=source_id, chunk_id=f"{source_id}-chunk", text=text, locator=json.dumps({"page": 3, "char_start": 7}), extraction_version=2, index_version=4))
            # Orphan index entries are never sufficient evidence.
            session.add(LexicalIndexEntry(source_id="missing", chunk_id="orphan", text=texts["keep"]))
            await session.commit()
            citation = await repo.add_citation(source_id="keep", text="Fixture citation.", project_id="default")
            result = await retrieve_literature_hits(
                session, query='"neural network" -survey',
                source_scope={"kind": "source-ids", "source_ids": ["keep", "exclude", "loose", "trashed", "missing"]},
                options=RetrievalOptions(semantic_enabled=True, offline_only=True, g3_enabled=True, query_filters=True),
            )
            assert [hit.source_id for hit in result.hits] == ["keep"]
            hit = result.hits[0]
            assert hit.text == texts["keep"]
            assert hit.citation_id == citation["id"]
            assert hit.locator == {"page": 3, "char_start": 7}
            assert hit.chunk_id == "keep-chunk"
            assert (hit.extraction_version, hit.index_version, hit.query_mode) == (2, 4, "lexical")
            legacy = await retrieve_literature_hits(
                session, query='"neural network" -survey',
                source_scope={"kind": "source-ids", "source_ids": ["keep", "exclude", "loose"]},
            )
            assert {hit.source_id for hit in legacy.hits} == {"keep", "exclude", "loose"}
            idea = IdeaGenerateStage(
                session=session, run_input=IdeaRunInput(topic='"neural network" -survey'),
                grounding=await _load_grounding(session, "default"), candidate_count=2,
                criteria=DEFAULT_RUBRIC_CRITERIA, scoring_method="pairwise", trust_origin="user",
            )
            idea_hits = await idea._retrieve(idea.run_input.topic)
            assert {"keep", "exclude", "loose"} <= {hit.source_id for hit in idea_hits}
            assert compile_plain_query('"neural network" -survey').confidence(texts["exclude"]) == 1.0
            assert not result.semantic_attempted
            assert result.offline_notice == "provider semantic search is unavailable offline"
    finally:
        await engine.dispose()


def test_real_api_ingest_phrase_and_exclusion_queries(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    with TestClient(create_app()) as client:
        saved = []
        for name, body in [
            ("keep.md", b"A neural network improves recall."),
            ("survey.md", b"A neural network survey improves recall."),
            ("loose.md", b"Neural methods support network recall."),
        ]:
            response = client.post("/api/sources/ingest", files={"file": (name, body, "text/markdown")})
            assert response.status_code == 200, response.text
            saved.append(response.json()["source"]["id"])
        result = client.get("/api/sources/retrieve", params={"query": '"neural network" -survey'})
        assert result.status_code == 200
        payload = result.json()
        assert [hit["source_id"] for hit in payload["hits"]] == [saved[0]]
        assert payload["chunks"] == ["A neural network improves recall."]
        assert payload["placeholder"] is False
        assert payload["notices"] == []
        scoped = client.get("/api/sources/retrieve", params={"query": '"neural network" -survey', "source_id": saved[1]}).json()
        assert scoped["hits"] == []
        invalid = client.get("/api/sources/retrieve", params={"query": '"unfinished'}).json()
        assert invalid["hits"] == []
        assert invalid["notices"][0].startswith("Invalid local search query:")
        plain = client.get("/api/sources/retrieve", params={"query": "neural network"}).json()
        assert {hit["source_id"] for hit in plain["hits"]} == set(saved)


def test_literature_review_exposes_invalid_query_notice_in_final_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    with TestClient(create_app()) as client:
        response = client.post("/api/recipes/literature-review/runs", json={"question": '"unfinished'})
        assert response.status_code == 200, response.text
        artifacts = [item for item in response.json()["artifacts"] if item["kind"] == "literature-review"]
        assert len(artifacts) == 1
        artifact = artifacts[0]
        assert artifact["retrieval_hits"] == []
        assert artifact["notices"] == ["Invalid local search query: Close the quoted phrase with a double quote."]
        assert artifact["notices"][0] in artifact["markdown"]
        assert all(not statements for statements in artifact["sections"].values())
