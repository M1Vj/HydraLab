import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from hydra.app import create_app
from hydra.research import normalize_arxiv_entry, normalize_openalex_work, normalize_unpaywall_work
from hydra.settings.consent import ConsentGates
from hydra.settings.indexing import resolve_indexing_policy
from hydra.settings.secrets import InMemorySecretStore, ProviderSecretService
from hydra.settings.toml_config import REQUIRED_SETTINGS_SECTIONS, SettingsValidationError, load_settings, save_settings
from hydra.storage.project import create_project
from hydra.storage.runtime import BackendRuntime, choose_bind_host


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
    claim = client.post("/api/claims", json={"text": "PaperQA supports cited scientific answers."}).json()
    response = client.post(
        "/api/evidence",
        json={
            "claim_id": claim["id"],
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
    assert listed[0]["claim_id"] == claim["id"]
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


def test_hl_core_05_settings_round_trip_preserves_unknown_keys_and_requires_sections(tmp_path):
    settings_path = tmp_path / "settings.toml"
    settings = {section: {} for section in REQUIRED_SETTINGS_SECTIONS}
    settings["schema"] = {"version": 1, "hydralab_version": "0.1.0"}
    settings["workspace"]["experimental_panels"] = ["graph", "timeline"]
    save_settings(settings_path, settings)

    loaded = load_settings(settings_path)
    save_settings(settings_path, loaded.data)
    reloaded = load_settings(settings_path)

    assert set(REQUIRED_SETTINGS_SECTIONS).issubset(reloaded.data)
    assert reloaded.data["workspace"]["experimental_panels"] == ["graph", "timeline"]

    invalid = tmp_path / "invalid.toml"
    missing_privacy = {section: {} for section in REQUIRED_SETTINGS_SECTIONS if section != "privacy"}
    missing_privacy["schema"] = {"version": 1, "hydralab_version": "0.1.0"}
    save_settings(invalid, missing_privacy, validate=False)

    with pytest.raises(SettingsValidationError, match=r"\[privacy\]"):
        load_settings(invalid)


def test_hl_core_08_single_instance_runtime_lock_reclaims_stale_and_never_binds_non_loopback(tmp_path):
    runtime = BackendRuntime(app_data_root=tmp_path, pid=123456789, port=8765)
    stale = runtime.acquire()
    assert stale.acquired is True
    assert stale.reclaimed_stale is True
    assert json.loads((tmp_path / "runtime" / "hydralab-backend.lock").read_text())["pid"] == 123456789

    second = BackendRuntime(app_data_root=tmp_path, pid=123456789, port=8766)
    blocked = second.acquire()
    assert blocked.acquired is False
    assert blocked.running_pid == 123456789
    assert choose_bind_host() == "127.0.0.1"


def test_hl_consent_01_gates_are_independent_and_offline_blocks_provider_send():
    gates = ConsentGates.defaults()

    assert gates.g1.local_research_indexing == "on"
    assert gates.g1.high_risk_indexing == "ask"
    assert gates.g2.local_browser_capture is False
    assert gates.g3.provider_send is False
    assert gates.can_send_to_provider(["active_file"]).allowed is False

    gates.g1.local_research_indexing = "on"
    gates.g2.local_browser_capture = True
    assert gates.g3.provider_send is False

    gates.g3.provider_send = True
    assert gates.can_send_to_provider(["active_file"]).allowed is True
    gates.offline_only = True
    decision = gates.can_send_to_provider(["active_file"])
    assert decision.allowed is False
    assert "offline-only" in decision.reason
    assert decision.status == "offline-locked"


@pytest.mark.parametrize(
    ("category", "status"),
    [
        ("sources", "indexed"),
        ("knowledge", "indexed"),
        ("code-folder", "needs-consent"),
        ("browser-history", "needs-consent"),
        (".git", "excluded"),
        ("credential-files", "excluded"),
    ],
)
def test_hl_consent_02_indexing_policy_classifies_by_consent(category, status):
    assert resolve_indexing_policy(category).status == status


def test_hl_lic_01_provider_secrets_store_only_references(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRALAB_APP_DATA_ROOT", str(tmp_path / "app-data"))
    project = create_project(tmp_path / "project", "Secret Test", git_enabled=False)
    secret_store = InMemorySecretStore()
    service = ProviderSecretService(secret_store)
    settings_path = tmp_path / "app-data" / "settings.toml"
    raw_secret = "sk-raw-secret-value"

    settings = service.save_provider_secret(
        settings_path=settings_path,
        provider_id="openai",
        secret_name="api_key",
        secret_value=raw_secret,
    )

    assert settings["providers"]["accounts"]["openai"]["secret_ref"] != raw_secret
    assert service.get_provider_secret(settings_path, "openai", "api_key") == raw_secret
    assert raw_secret not in settings_path.read_text()
    assert raw_secret not in (project.root / "project.yaml").read_text()

    conn = sqlite3.connect(project.root / ".hydralab" / "hydralab.db")
    try:
        dump = "\n".join(conn.iterdump())
    finally:
        conn.close()
    assert raw_secret not in dump

    runtime = BackendRuntime(app_data_root=tmp_path / "app-data", pid=123456789, port=8765)
    runtime.acquire()
    assert raw_secret not in (tmp_path / "app-data" / "runtime" / "hydralab-backend.lock").read_text()
