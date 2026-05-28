from fastapi.testclient import TestClient
from hydra.app import app

client = TestClient(app)

def test_chat_persistence():
    # List conversations (should be empty initially)
    resp = client.get("/api/chat/conversations")
    assert resp.status_code == 200
    assert len(resp.json()["conversations"]) == 0

    # Start a chat completion
    resp = client.post("/api/chat/completions", json={"message": "Hello!"})
    assert resp.status_code == 200
    
    # Read streaming response manually since TestClient doesn't automatically iterate streams gracefully here
    lines = resp.text.strip().split("\n\n")
    assert len(lines) > 0
    # The last chunk should have the conversation_id
    last_chunk = lines[-1].removeprefix("data: ")
    import json
    data = json.loads(last_chunk)
    assert data["type"] == "done"
    conv_id = data["conversation_id"]

    # List conversations again
    resp = client.get("/api/chat/conversations")
    assert resp.status_code == 200
    convs = resp.json()["conversations"]
    assert len(convs) > 0
    assert convs[0]["id"] == conv_id

    # List messages
    resp = client.get(f"/api/chat/conversations/{conv_id}/messages")
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello!"
    assert messages[1]["role"] == "assistant"
    assert "mock response" in messages[1]["content"]
