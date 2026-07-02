import json
import sqlite3

from fastapi.testclient import TestClient

from hydra.app import create_app
from hydra.services.assistant.consent import SendScopeItem, resolve_send_scope


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    monkeypatch.setenv("HYDRALAB_APP_DATA_ROOT", str(tmp_path / "app-data"))
    return TestClient(create_app())


def _enable_g3(client):
    from hydra.storage.app_data import app_data_root
    from hydra.settings.toml_config import load_settings, save_settings

    settings_path = app_data_root() / "settings.toml"
    settings = load_settings(settings_path).data
    settings["privacy"]["g3_provider_send"] = True
    save_settings(settings_path, settings)


# @HL-CONSENT-01 — with no opt-ins only the conservative allowlist is in scope.
def test_hl_consent_01_conservative_allowlist_only():
    items = [
        SendScopeItem("active_file", "drafts/intro.md"),
        SendScopeItem("selection", "drafts/intro.md#sel"),
        SendScopeItem("saved_chat", "chat-123"),
        SendScopeItem("pdf", "1706.03762.pdf"),
    ]
    scope = resolve_send_scope(items, g3_enabled=True, offline_only=False, opt_ins={})
    included_types = {i["type"] for i in scope.included}
    assert included_types == {"active_file", "selection"}
    excluded_types = {i["type"] for i in scope.excluded}
    assert "saved_chat" in excluded_types
    assert "pdf" in excluded_types


# @HL-CONSENT-02 — pre-send surface lists items; removal excludes them.
def test_hl_consent_02_presend_surface_lists_and_removes(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _enable_g3(client)
    refs = [
        {"type": "active_file", "id_or_path": "drafts/intro.md"},
        {"type": "selection", "id_or_path": "drafts/intro.md#sel"},
        {"type": "attachment", "id_or_path": "1706.03762", "label": "1706.03762"},
    ]
    surface = client.post("/api/assistant/send-scope", json={"context_refs": refs}).json()
    labels = {i["id_or_path"] for i in surface["included"]}
    assert {"drafts/intro.md", "drafts/intro.md#sel", "1706.03762"} <= labels

    # Removing the attachment client-side => send scope without it lists only two.
    reduced = client.post("/api/assistant/send-scope", json={"context_refs": refs[:2]}).json()
    reduced_labels = {i["id_or_path"] for i in reduced["included"]}
    assert "1706.03762" not in reduced_labels


# @HL-CONSENT-03 — offline-only hard-blocks sends and purges cache.
def test_hl_consent_03_offline_only_blocks_and_purges(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _enable_g3(client)
    toggled = client.post("/api/assistant/offline", params={"enabled": True}).json()
    assert toggled["offline_only"] is True
    assert toggled["cache_purged"] is True
    assert toggled["status"] == "offline-blocked"

    chat = client.post("/api/chats", json={"project_id": "p1", "name": "c"}).json()["chat"]
    response = client.post("/api/chat/completions", json={"chat_id": chat["id"], "message": "hi"})
    events = [json.loads(b[len("data:"):].strip()) for b in response.text.strip().split("\n\n") if b.strip().startswith("data:")]
    assert any(e["type"] == "blocked" and e.get("status") == "offline-blocked" for e in events)
    # No assistant content was produced.
    assert not any(e["type"] == "message" for e in events)

    modes = client.get("/api/assistant/modes").json()
    assert modes["offline_only"] is True


# @HL-CONSENT-03b — legacy research endpoints must honour offline_only (no scholarly egress).
def test_hl_consent_03b_offline_blocks_legacy_research_egress(tmp_path, monkeypatch):
    async def _must_not_call(*args, **kwargs):
        raise AssertionError("scholarly network must not be touched when offline_only is engaged")

    monkeypatch.setattr("hydra.research._openalex", _must_not_call)
    monkeypatch.setattr("hydra.research._arxiv", _must_not_call)
    monkeypatch.setattr("hydra.research._unpaywall", _must_not_call)
    client = _client(tmp_path, monkeypatch)
    client.post("/api/assistant/offline", params={"enabled": True})

    research = client.post("/api/chat/research", json={"query": "attention transformers"}).json()
    assert research["offline_blocked"] is True
    assert research["sources"][0]["id"].startswith("local_")

    search = client.post("/api/sources/search", json={"query": "attention"}).json()
    assert search["offline_blocked"] is True
    assert search["sources"][0]["id"].startswith("local_")


# @HL-CONSENT-03c — the Settings-panel offline toggle (workspace_preferences) must
# actually engage enforcement, not just persist an inert workspace key.
def test_hl_consent_03c_settings_offline_toggle_engages_enforcement(tmp_path, monkeypatch):
    async def _must_not_call(*args, **kwargs):
        raise AssertionError("scholarly network must not be touched when offline_only is engaged")

    monkeypatch.setattr("hydra.research._openalex", _must_not_call)
    monkeypatch.setattr("hydra.research._arxiv", _must_not_call)
    monkeypatch.setattr("hydra.research._unpaywall", _must_not_call)
    client = _client(tmp_path, monkeypatch)

    saved = client.post(
        "/api/settings",
        json={"workspace_preferences": {"offlineOnly": "true"}},
    )
    assert saved.status_code == 200

    # Enforcement surface reflects the toggle...
    modes = client.get("/api/assistant/modes").json()
    assert modes["offline_only"] is True

    # ...and the legacy scholarly egress paths are air-gapped.
    research = client.post("/api/chat/research", json={"query": "attention transformers"}).json()
    assert research["offline_blocked"] is True
    assert research["sources"][0]["id"].startswith("local_")


def test_hl_consent_03c_settings_offline_toggle_off_restores_online(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/settings", json={"workspace_preferences": {"offlineOnly": "true"}})
    assert client.get("/api/assistant/modes").json()["offline_only"] is True

    client.post("/api/settings", json={"workspace_preferences": {"offlineOnly": "false"}})
    assert client.get("/api/assistant/modes").json()["offline_only"] is False


# @HL-CONSENT-04 — granting only G2 does not make browser page text sendable.
def test_hl_consent_04_browser_page_text_separate_optin():
    items = [SendScopeItem("browser_event", "https://example.com/page", label="page")]
    # G2 granted locally, but browser_page_text opt-in off.
    scope = resolve_send_scope(items, g3_enabled=True, offline_only=False, opt_ins={})
    assert not scope.included
    assert any("browser_page_text" in i["reason"] for i in scope.excluded)
    # With the explicit opt-in, it becomes eligible.
    scope2 = resolve_send_scope(items, g3_enabled=True, offline_only=False, opt_ins={"browser_page_text": True})
    assert scope2.included


# @HL-CONSENT-05 — hard-blocked categories are refused with a reason, never dropped.
def test_hl_consent_05_credential_file_refused(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _enable_g3(client)
    response = client.post(
        "/api/assistant/send-scope",
        json={"context_refs": [{"type": "attachment", "id_or_path": ".env", "label": ".env"}]},
    )
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["kind"] == "hard-blocked"
    assert ".env" in detail["reason"]


def test_hl_consent_05_incognito_browser_refused():
    items = [SendScopeItem("browser_event", "https://x.test", locator={"incognito": True})]
    scope = resolve_send_scope(items, g3_enabled=True, offline_only=False, opt_ins={"browser_page_text": True})
    assert scope.has_hard_block
    assert "private/incognito" in scope.blocked[0]["reason"]


# @HL-CONSENT-06 — provider account stores metadata + secret_ref only; no raw secret on disk.
def test_hl_consent_06_no_raw_secret_persisted(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    raw = "sk-super-secret-key-value"
    ref = client.post("/api/settings/provider/secret", json={"provider": "openai", "secret": raw}).json()
    assert ref["secret_ref"] == "keychain:hydralab/openai"
    client.put("/api/settings/provider", json={"provider": "openai", "model": "gpt-4.1-mini", "api_key_ref": ref["secret_ref"]})

    settings = client.get("/api/settings").json()
    assert raw not in json.dumps(settings)
    provider_row = next(p for p in settings["provider_settings"] if p["provider"] == "openai")
    assert provider_row["secret_ref"] == "keychain:hydralab/openai"

    from hydra.storage.app_data import app_data_root

    settings_toml = (app_data_root() / "settings.toml").read_text()
    assert raw not in settings_toml
    db_path = tmp_path / "hydra.db"
    conn = sqlite3.connect(db_path)
    try:
        dump = "\n".join(conn.iterdump())
    finally:
        conn.close()
    assert raw not in dump


# @HL-CONSENT-01 (G3 off) — nothing is in scope when the gate is off.
def test_g3_off_blocks_all():
    items = [SendScopeItem("active_file", "a.md"), SendScopeItem("selection", "a.md#s")]
    scope = resolve_send_scope(items, g3_enabled=False, offline_only=False, opt_ins={})
    assert not scope.included
    assert all("G3" in i["reason"] for i in scope.excluded)
