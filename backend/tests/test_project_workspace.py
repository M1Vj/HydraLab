from fastapi.testclient import TestClient

from hydra.app import create_app


def test_project_objects_aggregates_repository_records(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    source = client.post("/api/sources/search", json={"query": "workspace shell"}).json()["sources"][0]
    note = client.post(
        "/api/notes",
        json={"title": "Workspace note", "body": "A real note body.", "source_id": source["id"]},
    ).json()
    task = client.post("/api/tasks", json={"title": "Review route wiring", "column": "to_do"}).json()
    claim = client.post("/api/claims", json={"text": "The workspace uses real objects."}).json()
    citation = client.post("/api/citations", json={"source_id": source["id"], "text": "Citation text."}).json()
    client.post(
        "/api/evidence",
        json={
            "claim_id": claim["id"],
            "citation_id": citation["id"],
            "source_id": source["id"],
            "passage": "Evidence passage.",
            "support": "supported",
            "confidence": 0.8,
        },
    )

    response = client.get("/api/project/objects")

    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"]["sources"] >= 1
    assert payload["counts"]["notes"] == 1
    assert payload["counts"]["tasks"] == 1
    assert payload["counts"]["claims"] == 1
    assert payload["counts"]["citations"] == 1
    assert payload["counts"]["evidence"] == 1
    assert payload["objects"]["notes"][0]["id"] == note["id"]
    assert payload["objects"]["tasks"][0]["id"] == task["id"]


def test_project_tree_lists_files_and_honors_runtime_exclusions(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "note.md").write_text("# Note", encoding="utf-8")
    (tmp_path / ".hydralab" / "temp").mkdir(parents=True)
    (tmp_path / ".hydralab" / "temp" / "draft.note-recovery.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
    client = TestClient(create_app())

    response = client.get("/api/project/tree")

    assert response.status_code == 200
    payload = response.json()
    paths = {node["path"]: node for node in payload["nodes"]}
    assert "knowledge" in paths
    assert paths["knowledge/note.md"]["index_status"] == "indexed"
    assert ".hydralab/temp/draft.note-recovery.json" not in paths
    assert ".git/HEAD" not in paths


def test_review_inbox_includes_repository_items_and_recovery_journals(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    recovery_dir = tmp_path / ".hydralab" / "temp"
    recovery_dir.mkdir(parents=True)
    recovery_dir.joinpath("draft.note-recovery.json").write_text(
        '{"id":"draft","note_id":"note_1","relative_path":"knowledge/note.md","content":"Recovered","status":"pending"}',
        encoding="utf-8",
    )
    client = TestClient(create_app())
    client.post(
        "/api/browser/propose-source",
        json={
            "project_id": "default",
            "url": "https://example.test/paper",
            "title": "Paper",
            "page_text": "save this as a source",
            "browser_integration_enabled": True,
            "g2_local_capture": True,
            "host_permission": "allow-for-project",
        },
        headers={"origin": "http://127.0.0.1:5173", "authorization": "Bearer missing"},
    )
    client.post("/api/sources/save", json={"project_id": "default", "query": "", "result": {"title": "Needs review"}})

    response = client.get("/api/review-inbox")

    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"]["pending"] >= 2
    item_types = {item["item_type"] for item in payload["items"]}
    assert "note-recovery" in item_types
    assert "source-save-proposal" in item_types
