import pytest
from fastapi.testclient import TestClient
from hydra.app import create_app

def test_claims_citations_and_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    # Create a claim
    claim = client.post("/api/claims", json={"text": "This is a test claim."}).json()
    assert claim["text"] == "This is a test claim."

    # Create a source
    source = client.post("/api/sources/search", json={"query": "test source"}).json()["sources"][0]

    # Create a citation
    citation = client.post("/api/citations", json={"source_id": source["id"], "text": "This is a citation."}).json()
    assert citation["text"] == "This is a citation."
    assert citation["source_id"] == source["id"]

    # Link evidence
    evidence = client.post(
        "/api/evidence",
        json={
            "claim_id": claim["id"],
            "citation_id": citation["id"],
            "source_id": source["id"],
            "passage": "This passage supports the claim.",
            "support": "supported",
            "confidence": 0.95
        }
    ).json()

    assert evidence["claim_id"] == claim["id"]
    assert evidence["citation_id"] == citation["id"]
    assert evidence["support"] == "supported"

    # Test lists
    claims_list = client.get("/api/claims").json()["claims"]
    assert len(claims_list) == 1
    assert claims_list[0]["id"] == claim["id"]

    citations_list = client.get("/api/citations").json()["citations"]
    assert len(citations_list) == 1
    assert citations_list[0]["id"] == citation["id"]

    evidence_list = client.get("/api/evidence").json()["evidence"]
    assert len(evidence_list) == 1
    assert evidence_list[0]["id"] == evidence["id"]

def test_detect_claims(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    response = client.post("/api/claims/detect", json={"text": "Draft text with claims."})
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["claims"]) == 2
    assert len(data["evidence"]) == 2
    assert data["evidence"][0]["support"] in ["supported", "unsupported"]
