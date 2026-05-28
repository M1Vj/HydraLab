from fastapi.testclient import TestClient

from hydra.app import create_app


def test_research_chat_returns_cited_answer_and_trace_event(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    response = client.post("/api/chat/research", json={"query": "retrieval augmented generation"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"]
    assert payload["citations"]
    assert payload["status"] == "completed"
    assert payload["citations"][0]["source_id"]

    events = client.get("/api/events").json()["events"]
    assert any(event["kind"] == "research.completed" for event in events)


def test_writing_review_flags_claims_and_rewrites_text(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    response = client.post(
        "/api/writing/review",
        json={"text": "This proves the method is always best. It is very good."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "always" in payload["unsupported_claims"][0].lower()
    assert payload["rewrite"] != "This proves the method is always best. It is very good."
    assert payload["critique"]


def test_sources_notes_tasks_paper_and_bibliography_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    sources = client.post("/api/sources/search", json={"query": "graph search"}).json()["sources"]
    assert sources[0]["title"]

    paper = client.post(
        "/api/sources/ingest",
        files={"file": ("paper.txt", b"Graph search improves exploration.", "text/plain")},
    ).json()
    assert paper["source"]["kind"] == "pdf"

    note = client.post(
        "/api/notes",
        json={"title": "Search note", "body": "Graph search improves exploration.", "source_id": paper["source"]["id"]},
    ).json()
    assert note["source_id"] == paper["source"]["id"]

    notes = client.get("/api/notes", params={"query": "exploration"}).json()["notes"]
    assert notes[0]["id"] == note["id"]

    task = client.post("/api/tasks", json={"title": "Review paper", "column": "To Do"}).json()
    moved = client.patch(f"/api/tasks/{task['id']}", json={"column": "Done", "progress": 100}).json()
    assert moved["column"] == "Done"
    assert moved["progress"] == 100

    bib = client.get("/api/export/bibliography", params={"style": "bibtex"}).text
    assert "@article" in bib or "@misc" in bib

def test_reviews_analyze(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())
    res = client.post("/api/reviews/analyze", json={"text": "This always proves the point!"})
    assert res.status_code == 200
    data = res.json()
    assert "categories" in data
    assert "unsupported_claims" in data

def test_notes_crud_and_links(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    # Create note 1
    note1 = client.post(
        "/api/notes",
        json={"title": "Note A", "body": "This is Note A body."},
    ).json()
    assert note1["id"]
    assert note1["title"] == "Note A"

    # Create note 2 with a wiki link to note 1 by title or by id
    note2 = client.post(
        "/api/notes",
        json={"title": "Note B", "body": f"This is Note B, linked to [[Note A]] and [[{note1['id']}]]."},
    ).json()
    assert note2["id"]

    # Get single note
    got = client.get(f"/api/notes/{note1['id']}").json()
    assert got["title"] == "Note A"

    # Search notes
    searched = client.get("/api/notes", params={"query": "Note B"}).json()["notes"]
    assert len(searched) == 1
    assert searched[0]["id"] == note2["id"]

    # Check backlinks for note 1
    links = client.get(f"/api/notes/{note1['id']}/links").json()
    assert len(links["backlinks"]) == 1
    assert links["backlinks"][0]["id"] == note2["id"]

    # Check graph
    graph = client.get("/api/notes/graph").json()
    assert len(graph["nodes"]) >= 2
    assert len(graph["links"]) >= 1

    # Update note 1
    updated = client.put(
        f"/api/notes/{note1['id']}",
        json={"title": "Note A Updated", "body": "New body content.", "source_id": None},
    ).json()
    assert updated["title"] == "Note A Updated"

    # Delete note 2
    deleted = client.delete(f"/api/notes/{note2['id']}").json()
    assert deleted["status"] == "success"

    # Ensure 404
    res = client.get(f"/api/notes/{note2['id']}")
    assert res.status_code == 404

def test_settings_get_post_and_export_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    client = TestClient(create_app())

    # Get settings (should be empty initially or contain defaults)
    settings = client.get("/api/settings").json()
    assert "provider_settings" in settings
    assert "workspace_preferences" in settings

    # Post settings updates
    post_payload = {
        "provider_settings": [
            {"provider": "openai", "model": "gpt-4o", "api_key_ref": "sk-12345"},
            {"provider": "gemini", "model": "gemini-1.5-pro", "api_key_ref": "ai-67890"}
        ],
        "workspace_preferences": {
            "theme": "dark",
            "default_provider": "openai",
            "system_instruction": "Be extremely precise."
        }
    }
    update_res = client.post("/api/settings", json=post_payload)
    assert update_res.status_code == 200
    updated_settings = update_res.json()
    
    # Check that settings are persisted and returned
    assert len(updated_settings["provider_settings"]) == 2
    assert updated_settings["workspace_preferences"]["theme"] == "dark"
    assert updated_settings["workspace_preferences"]["default_provider"] == "openai"
    assert updated_settings["workspace_preferences"]["system_instruction"] == "Be extremely precise."

    # Verify that the GET endpoint returns the updated settings
    got_settings = client.get("/api/settings").json()
    assert len(got_settings["provider_settings"]) == 2
    assert got_settings["workspace_preferences"]["theme"] == "dark"

    # Add a mock note and task to check export
    note = client.post(
        "/api/notes",
        json={"title": "Exportable Note", "body": "This body should be inside notes/Exportable Note.md in ZIP."},
    ).json()
    assert note["id"]

    task = client.post(
        "/api/tasks",
        json={"title": "Exportable Task", "column": "to_do", "detail": "Test detail of task."}
    ).json()
    assert task["id"]

    # Check export preview
    preview = client.get("/api/export/preview").json()
    assert preview["counts"]["notes"] == 1
    assert preview["counts"]["tasks"] == 1
    assert "notes/Exportable Note.md" in preview["files"]
    assert "citations.md" in preview["files"]
    assert "tasks.md" in preview["files"]
    assert "metadata.json" in preview["files"]

    # Check actual ZIP export
    export_res = client.post("/api/export")
    assert export_res.status_code == 200
    assert export_res.headers["content-type"] == "application/zip"
    
    # Parse the ZIP file to ensure contents are correct
    import zipfile
    import io
    import json
    
    zip_bytes = export_res.content
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        # Check files
        file_list = z.namelist()
        assert "notes/Exportable Note.md" in file_list
        assert "citations.md" in file_list
        assert "tasks.md" in file_list
        assert "metadata.json" in file_list
        
        # Verify note content
        note_content = z.read("notes/Exportable Note.md").decode("utf-8")
        assert "# Exportable Note" in note_content
        assert "This body should be inside notes/Exportable Note.md" in note_content
        
        # Verify metadata scrubbed provider_settings
        meta = json.loads(z.read("metadata.json").decode("utf-8"))
        assert len(meta["notes"]) == 1
        assert len(meta["tasks"]) == 1
        assert len(meta["provider_settings"]) == 2
        # Verify API keys refs are preserved!
        p_map = {p["provider"]: p for p in meta["provider_settings"]}
        assert p_map["openai"]["api_key_ref"] == "sk-12345"
        assert p_map["gemini"]["api_key_ref"] == "ai-67890"



