from fastapi.testclient import TestClient
from hydra.app import create_app

def test_rag_ingest_url_and_retrieve(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    response = client.post("/api/sources/ingest", data={"url": "https://example.com/paper.pdf", "title": "Example Paper"})
    assert response.status_code == 501
    assert "discovery auto-download" in response.json()["detail"]
    
    retrieve_response = client.get("/api/sources/retrieve", params={"query": "RAG architecture", "source_id": "src-placeholder"})
    assert retrieve_response.status_code == 200
    rag_payload = retrieve_response.json()
    assert rag_payload["query"] == "RAG architecture"
    assert rag_payload["source_id"] == "src-placeholder"
    assert rag_payload["placeholder"] is True
    assert "Placeholder retrieval response" in rag_payload["answer"]
    assert len(rag_payload["chunks"]) > 0
