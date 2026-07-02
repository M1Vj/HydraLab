from fastapi.testclient import TestClient

from hydra.app import create_app


def test_rag_retrieve_returns_real_indexed_passages(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    body = (
        b"# RAG Notes\n\n"
        b"Retrieval augmented generation grounds a language model in retrieved "
        b"source passages so the answer is traceable to real documents.\n"
    )
    ingested = client.post(
        "/api/sources/ingest",
        files={"file": ("rag-notes.md", body, "text/markdown")},
    )
    assert ingested.status_code == 200, ingested.text
    source_id = ingested.json()["source"]["id"]

    response = client.get("/api/sources/retrieve", params={"query": "retrieval augmented generation"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["placeholder"] is False
    # A real passage from the ingested source is returned — not fabricated text.
    assert any(hit["source_id"] == source_id for hit in payload["hits"])
    assert any("retrieval augmented generation" in chunk.lower() for chunk in payload["chunks"])
    assert "Retrieval augmented generation" in payload["answer"]

    # A term that only appears deep in a long document is still retrievable,
    # proving the whole document is chunked and indexed (not just a prefix).
    long_body = ("# Long Paper\n\n" + ("Filler sentence about methods. " * 400)).encode() + (
        b"\n\nThe unique marker phrase zebrafinch appears only near the very end."
    )
    client.post("/api/sources/ingest", files={"file": ("long.md", long_body, "text/markdown")})
    deep = client.get("/api/sources/retrieve", params={"query": "zebrafinch"}).json()
    assert deep["hits"], "a term deep in the document must be retrievable"
    assert any("zebrafinch" in chunk.lower() for chunk in deep["chunks"])

    # Honest empty result: an unmatched query invents nothing.
    miss = client.get("/api/sources/retrieve", params={"query": "zzznonexistentterm"}).json()
    assert miss["placeholder"] is False
    assert miss["hits"] == []
    assert "No indexed passages matched" in miss["answer"]

    # An unknown source_id yields no hits rather than inventing one.
    scoped = client.get(
        "/api/sources/retrieve",
        params={"query": "retrieval", "source_id": "src-does-not-exist"},
    ).json()
    assert scoped["hits"] == []


def test_rag_ingest_url_is_not_yet_supported(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    response = client.post(
        "/api/sources/ingest",
        data={"url": "https://example.com/paper.pdf", "title": "Example Paper"},
    )
    assert response.status_code == 501
    assert "discovery auto-download" in response.json()["detail"]
