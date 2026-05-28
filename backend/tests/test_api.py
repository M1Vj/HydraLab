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

