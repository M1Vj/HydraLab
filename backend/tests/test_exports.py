"""Feature 01-11 (11d) — clean handoff exports + safe SQLite backup.

Covers @HL-EXPORT-01..06.
"""
import io
import sqlite3
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from hydra.app import create_app
from hydra.services.export import (
    build_project_zip,
    export_options,
    safe_sqlite_backup,
    to_bibtex,
    to_csl_json,
    to_ris,
)
from hydra.services.export.bundle import ExportOptions, scrub_secret_text, should_exclude


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    return TestClient(create_app())


_ATTENTION = {
    "id": "src1",
    "title": "Attention Is All You Need",
    "authors": ["Ashish Vaswani", "Noam Shazeer"],
    "year": "2017",
    "doi": "10.48550/arXiv.1706.03762",
    "url": "https://arxiv.org/abs/1706.03762",
}


# @HL-EXPORT-01 -------------------------------------------------------------
def test_hl_export_01_bibtex_includes_title_and_doi():
    bibtex = to_bibtex([_ATTENTION])
    assert "Attention Is All You Need" in bibtex
    assert "10.48550/arXiv.1706.03762" in bibtex
    assert bibtex.startswith("@article{")


def test_hl_export_01_csl_and_ris_are_valid():
    import json

    csl = json.loads(to_csl_json([_ATTENTION]))
    assert csl[0]["title"] == "Attention Is All You Need"
    assert csl[0]["DOI"] == "10.48550/arXiv.1706.03762"
    assert csl[0]["issued"]["date-parts"] == [[2017]]

    ris = to_ris([_ATTENTION])
    assert "TY  - JOUR" in ris
    assert "TI  - Attention Is All You Need" in ris
    assert "DO  - 10.48550/arXiv.1706.03762" in ris
    assert ris.strip().endswith("ER  -")


# @HL-EXPORT-02 -------------------------------------------------------------
def test_hl_export_02_project_zip_contains_only_selected_files(tmp_path):
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "drafts").mkdir()
    (tmp_path / "knowledge" / "index.md").write_text("# Index\n")
    (tmp_path / "drafts" / "intro.md").write_text("# Intro\n")
    (tmp_path / "drafts" / "scratch.md").write_text("scratch\n")

    data = build_project_zip(tmp_path, selected_files=["knowledge/index.md", "drafts/intro.md"])
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert "knowledge/index.md" in names
    assert "drafts/intro.md" in names
    assert "drafts/scratch.md" not in names


# @HL-EXPORT-03 -------------------------------------------------------------
def test_hl_export_03_docx_slot_shows_setup_required(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    options = client.get("/api/export/options").json()
    docx = next(f for f in options["bundle_formats"] if f["id"] == "docx")
    assert docx["available"] is False
    assert docx["state"] == "setup required"


# @HL-EXPORT-04 -------------------------------------------------------------
def test_hl_export_04_clean_zip_excludes_caches_and_secrets(tmp_path, monkeypatch):
    (tmp_path / ".hydralab" / "cache").mkdir(parents=True)
    (tmp_path / ".hydralab" / "cache" / "vectors.bin").write_text("cache")
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "index.md").write_text("# Index\n")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-livesecretkey1234567890\n")

    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/export/project-zip", json={})
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert "knowledge/index.md" in names
    assert not any(name.startswith(".hydralab/cache") for name in names)
    assert ".env" not in names
    blob = b"".join(archive.read(name) for name in names)
    assert b"sk-livesecretkey1234567890" not in blob


def test_hl_export_04_should_exclude_rules():
    assert should_exclude(".hydralab/cache/x.bin") is True
    assert should_exclude(".env") is True
    assert should_exclude(".git/config") is True
    assert should_exclude("work/chats/session.md") is True  # opt-in default off
    assert should_exclude("work/chats/session.md", ExportOptions(include_chats=True)) is False
    assert should_exclude("knowledge/index.md") is False


def test_hl_export_04_should_exclude_matches_nested_excluded_dirs():
    # Privacy audit H2: nested/submodule .git and vendored node_modules must be
    # excluded at ANY depth, not only when they are the first path segment.
    assert should_exclude("apps/web/.git/config") is True
    assert should_exclude("vendor/lib/node_modules/pkg/index.js") is True
    assert should_exclude("sub/proj/.venv/pyvenv.cfg") is True
    assert should_exclude("deep/nested/.hydralab/cache/x.bin") is True


def test_hl_export_04_scrub_secret_text_catches_quoted_embedded_and_pem():
    # Privacy audit H3: quoted, URL-embedded, Google and PEM-block secrets must be
    # redacted, not only bare whitespace-delimited tokens.
    samples = [
        '{"api_key":"sk-proj-abcdefgh1234567890"}',
        "url = https://x-access-token:ghp_abcdefghij0123456789abcd@github.com/o/r.git",
        "export KEY=AIzaSyA1234567890abcdefghij1234567890ABCDE",
        "-----BEGIN OPENSSH PRIVATE KEY-----\nMIIabc123secretbody\n-----END OPENSSH PRIVATE KEY-----",
    ]
    for sample in samples:
        scrubbed = scrub_secret_text(sample)
        assert "[REDACTED-SECRET]" in scrubbed
    joined = scrub_secret_text("\n".join(samples))
    for leaked in ("sk-proj-abcdefgh", "ghp_abcdefghij", "AIzaSyA1234567890", "MIIabc123secretbody"):
        assert leaked not in joined


# @HL-EXPORT-06 -------------------------------------------------------------
def test_hl_export_06_sqlite_backup_during_write_opens_without_corruption(tmp_path):
    src = tmp_path / "hydra.db"
    conn = sqlite3.connect(str(src))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('a')")
    conn.commit()

    # Simulate a concurrent indexing write holding an open transaction.
    writer = sqlite3.connect(str(src))
    writer.execute("BEGIN")
    writer.execute("INSERT INTO t (v) VALUES ('mid-write')")

    dest = tmp_path / "backups" / "backup.db"
    result = safe_sqlite_backup(src, dest)
    writer.rollback()
    writer.close()
    conn.close()

    assert result["integrity_ok"] is True
    assert result["live_file_copied"] is False
    assert result["method"] == "sqlite-online-backup"
    verify = sqlite3.connect(str(dest))
    assert verify.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    verify.close()


# @HL-EXPORT-05 -------------------------------------------------------------
def test_hl_export_05_restore_reopens_and_rebuilds_index(tmp_path, monkeypatch):
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "note.md").write_text(
        "---\nnote_id: note-restore-1\ntitle: Restored Note\n---\n\n# Restored Note\n\nScaling laws.\n"
    )
    client = _client(tmp_path, monkeypatch)
    result = client.post("/api/restore", json={"reindex": True}).json()
    assert result["reopened"] is True
    assert any(step["step"] == "reindex" and step["status"] == "done" for step in result["progress"])
    assert "note-restore-1" in result["reindexed"]

    notes = client.get("/api/notes").json()["notes"]
    assert any(n["id"] == "note-restore-1" for n in notes)


def test_export_options_lists_citation_formats():
    options = export_options()
    assert set(options["citation_formats"]) == {"bibtex", "csl", "ris"}
