import json

import pytest
from fastapi.testclient import TestClient

from hydra.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    monkeypatch.setenv("HYDRALAB_APP_DATA_ROOT", str(tmp_path / "app-data"))
    return TestClient(create_app())


def _stream_events(response):
    events = []
    for block in response.text.strip().split("\n\n"):
        line = block.strip()
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


# @HL-ASSIST-01 — a new project opens with exactly one default chat, persisted.
def test_hl_assist_01_default_chat_autocreated_and_persists(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    chats = client.get("/api/chats", params={"project_id": "diffusion-survey"}).json()["chats"]
    assert len(chats) == 1
    assert chats[0]["name"] == "default"
    # Reload (new list call) still returns exactly one default chat.
    reloaded = client.get("/api/chats", params={"project_id": "diffusion-survey"}).json()["chats"]
    assert len(reloaded) == 1
    assert reloaded[0]["id"] == chats[0]["id"]


# @HL-ASSIST-02 — an archived chat remains findable by search.
def test_hl_assist_02_archived_chat_still_searchable(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    chat = client.post("/api/chats", json={"project_id": "p1", "name": "related work"}).json()["chat"]
    client.patch(f"/api/chats/{chat['id']}", json={"archived": True})
    results = client.get("/api/chats/search", params={"project_id": "p1", "q": "related"}).json()["chats"]
    hit = next((c for c in results if c["id"] == chat["id"]), None)
    assert hit is not None
    assert hit["archived"] is True


def test_hl_assist_02_rename_chat(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    chat = client.post("/api/chats", json={"project_id": "p1", "name": "draft"}).json()["chat"]
    renamed = client.patch(f"/api/chats/{chat['id']}", json={"name": "methods"}).json()["chat"]
    assert renamed["name"] == "methods"


# @HL-ASSIST-03 — completed turns persist incrementally; the streamed prefix is retained.
def test_hl_assist_03_incremental_persistence_keeps_completed_turns(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    chat = client.post("/api/chats", json={"project_id": "p1", "name": "methods"}).json()["chat"]
    for _ in range(3):
        client.post("/api/chat/completions", json={"chat_id": chat["id"], "message": "prior turn"})
    messages = client.get(f"/api/chats/{chat['id']}/messages").json()["messages"]
    # 3 turns => 3 user + 3 assistant messages, all persisted.
    assert len([m for m in messages if m["role"] == "user"]) == 3
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert len(assistant_msgs) == 3
    assert all(m["content"] for m in assistant_msgs)


@pytest.mark.asyncio
async def test_hl_assist_03_force_quit_midstream_keeps_prefix(tmp_path, monkeypatch):
    """Consuming only a prefix of the stream still persists that prefix (force-quit)."""
    from hydra.database.session import async_session_maker
    from hydra.database.repository import Repository
    from hydra.providers import MockProvider, ProviderRouter, RoutingPolicy
    from hydra.services.assistant import AssistantConfig, AssistantService

    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    from hydra.database.session import init_db

    await init_db()
    async with async_session_maker() as session:
        repo = Repository(session)
        chat = await repo.ensure_default_chat("p1")
        for i in range(3):
            await repo.add_chat_message(chat["id"], "user", f"turn {i}")
            await repo.add_chat_message(chat["id"], "assistant", f"answer {i}", trust_origin="assistant")
        row = await repo.add_chat_message(chat["id"], "assistant", "", trust_origin="assistant")
        message_id = row["id"]

    service = AssistantService(
        router=ProviderRouter(providers=[MockProvider()], policy=RoutingPolicy(mode="single")),
        config=AssistantConfig(g3_enabled=True),
    )

    async def persist(delta):
        async with async_session_maker() as bg:
            await Repository(bg).append_chat_message_content(message_id, delta)

    consumed = 0
    async for event in service.stream_reply("The IMU baseline uses", on_delta=persist):
        if event.get("type") == "message":
            consumed += 1
            if consumed >= 2:
                break  # simulate force-quit mid-stream

    async with async_session_maker() as session:
        messages = await Repository(session).list_chat_messages(chat["id"])
    completed = [m for m in messages if m["role"] == "assistant" and m["id"] != message_id]
    assert len(completed) == 3  # all prior completed turns retained
    inflight = next(m for m in messages if m["id"] == message_id)
    assert inflight["content"]  # the streamed prefix persisted


# @HL-ASSIST-04 — editing an exported artifact does not mutate the canonical chat.
def test_hl_assist_04_export_artifact_is_non_authoritative(tmp_path, monkeypatch):
    from pathlib import Path

    client = _client(tmp_path, monkeypatch)
    chat = client.post("/api/chats", json={"project_id": "p1", "name": "methods"}).json()["chat"]
    client.post("/api/chat/completions", json={"chat_id": chat["id"], "message": "hello methods"})
    export = client.post(f"/api/chats/{chat['id']}/export", json={}).json()
    artifact_path = Path(tmp_path) / export["path"]
    assert artifact_path.exists()
    text = artifact_path.read_text()
    assert f"chat_id: {chat['id']}" in text
    assert "authoritative: false" in text

    # Edit the export on disk.
    artifact_path.write_text(text + "\n\nEDITED BY USER OUTSIDE HYDRALAB")
    messages = client.get(f"/api/chats/{chat['id']}/messages").json()["messages"]
    assert all("EDITED BY USER OUTSIDE HYDRALAB" not in m["content"] for m in messages)


# @HL-ASSIST-05 — the context picker records a chosen source as a context reference.
def test_hl_assist_05_context_refs_recorded_on_message(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    chat = client.post("/api/chats", json={"project_id": "p1", "name": "related work"}).json()["chat"]
    client.post(
        "/api/chat/completions",
        json={
            "chat_id": chat["id"],
            "message": "summarize",
            "context_refs": [{"type": "source", "id_or_path": "Attention Is All You Need", "label": "Attention Is All You Need"}],
        },
    )
    messages = client.get(f"/api/chats/{chat['id']}/messages").json()["messages"]
    user = next(m for m in messages if m["role"] == "user")
    assert user["context_refs"][0]["type"] == "source"
    assert user["context_refs"][0]["id_or_path"] == "Attention Is All You Need"


# @HL-MODE-01 — Phase 2 adds Co-pilot; Full Access stays per-project opt-in (OFF).
def test_hl_mode_01_passive_only_mode(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    modes = client.get("/api/assistant/modes").json()
    assert modes["default_mode"] == "passive"
    by_id = {m["id"]: m for m in modes["modes"]}
    assert by_id["passive"]["enabled"] is True
    # Phase 2 lands Co-pilot as a selectable mode.
    assert by_id["copilot"]["enabled"] is True
    assert by_id["copilot"]["phase"] == 2
    # Full Access defaults OFF until explicitly enabled for the project.
    assert by_id["full_access"]["enabled"] is False
    assert modes["full_access_enabled"] is False
    # Honesty: with no BYO provider key, replies come from the local mock
    # placeholder, so the UI must be told the provider is not configured.
    assert modes["provider_configured"] is False
    assert modes["active_provider"] == "mock"


# @HL-MODE-02 — the assistant streams a reply in Passive mode.
def test_hl_mode_02_assistant_streams_reply(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    chat = client.post("/api/chats", json={"project_id": "p1", "name": "chat"}).json()["chat"]
    response = client.post("/api/chat/completions", json={"chat_id": chat["id"], "message": "what is diffusion"})
    events = _stream_events(response)
    assert any(e["type"] == "message" for e in events)
    done = [e for e in events if e["type"] == "done"]
    assert done and done[0]["chat_id"] == chat["id"]
