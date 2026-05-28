import json

import pytest
from fastapi.testclient import TestClient

from hydra.app import create_app
from hydra.research import normalize_arxiv_entry, normalize_openalex_work, normalize_unpaywall_work


def test_normalizes_openalex_arxiv_and_unpaywall_sources():
    openalex = normalize_openalex_work(
        {
            "id": "https://openalex.org/W123",
            "title": "PaperQA",
            "publication_year": 2023,
            "doi": "https://doi.org/10.48550/arxiv.2312.07559",
            "authorships": [{"author": {"display_name": "A. Author"}}],
            "abstract_inverted_index": {"retrieval": [0], "works": [1]},
        }
    )
    arxiv = normalize_arxiv_entry(
        {
            "id": "2312.07559v1",
            "title": "PaperQA: Retrieval-Augmented Generative Agent",
            "authors": ["Jakub Lala", "Sam Cox"],
            "published": "2023-12-12T00:00:00Z",
            "summary": "Agentic retrieval over papers.",
            "url": "https://arxiv.org/abs/2312.07559",
        }
    )
    unpaywall = normalize_unpaywall_work(
        {
            "doi": "10.1038/example",
            "title": "Open access work",
            "year": 2024,
            "z_authors": [{"given": "Ada", "family": "Lovelace"}],
            "best_oa_location": {"url_for_pdf": "https://example.test/paper.pdf"},
        }
    )

    assert openalex["id"] == "openalex_W123"
    assert openalex["abstract"] == "retrieval works"
    assert arxiv["id"] == "arxiv_2312.07559"
    assert arxiv["kind"] == "preprint"
    assert unpaywall["id"] == "unpaywall_10_1038_example"
    assert unpaywall["url"] == "https://example.test/paper.pdf"


def test_evidence_records_claim_support_and_review_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    source = client.post("/api/sources/search", json={"query": "paperqa"}).json()["sources"][0]
    response = client.post(
        "/api/evidence",
        json={
            "claim": "PaperQA supports cited scientific answers.",
            "source_id": source["id"],
            "passage": "PaperQA is a retrieval-augmented agent for scientific research.",
            "support": "supported",
            "confidence": 0.86,
        },
    )

    assert response.status_code == 200
    evidence = response.json()
    assert evidence["support"] == "supported"
    assert evidence["review_status"] == "needs_review"

    listed = client.get("/api/evidence").json()["evidence"]
    assert listed[0]["claim"] == "PaperQA supports cited scientific answers."
    assert listed[0]["source_title"]


def test_settings_persist_without_storing_secret_values_and_export_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    saved = client.put(
        "/api/settings/provider",
        json={
            "provider": "openai",
            "model": "gpt-5.1",
            "api_key": "sk-secret-value",
            "api_key_ref": "env:OPENAI_API_KEY",
        },
    ).json()

    assert saved["provider"] == "openai"
    assert saved["api_key_ref"] == "env:OPENAI_API_KEY"
    assert "sk-secret-value" not in json.dumps(saved)

    settings = client.get("/api/settings").json()["provider_settings"]
    assert settings[0]["model"] == "gpt-5.1"
    assert "sk-secret-value" not in json.dumps(settings)

    client.post("/api/tasks", json={"title": "Trace task", "column": "Review"})
    export = client.get("/api/export/workspace").json()
    assert export["provider_settings"][0]["api_key_ref"] == "env:OPENAI_API_KEY"
    assert export["tasks"][0]["title"] == "Trace task"
