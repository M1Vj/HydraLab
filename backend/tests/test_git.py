"""Feature 01-11 (11b) — safe Git panel with hybrid init/detect.

Covers @HL-GIT-01..05. Function names carry ``git`` + ``init``/``detect`` so the
guide's ``-k "git and (init or detect)"`` gate selects the init/detect proofs, and
the destructive proof carries ``console`` so ``-k "console or verify or safe"``
confirms reset is unreachable from the console.
"""
import os
import subprocess

from fastapi.testclient import TestClient

from hydra.app import create_app
from hydra.services.git import GitService


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("HYDRA_HOME", str(tmp_path))
    return TestClient(create_app())


def _init_repo(root):
    service = GitService(root)
    service._run(["init"])
    service._run(["config", "user.email", "test@hydralab.local"])
    service._run(["config", "user.name", "HydraLab Test"])
    return service


# @HL-GIT-02 ----------------------------------------------------------------
def test_hl_git_02_opening_non_git_folder_prompts_before_init_and_detect(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert not (tmp_path / ".git").exists()

    ask = client.post("/api/git/init", json={"confirm": False}).json()
    assert ask["action"] == "ask"
    assert ask["initialized"] is False
    assert not (tmp_path / ".git").exists()  # never silently initialized

    confirmed = client.post("/api/git/init", json={"confirm": True}).json()
    assert confirmed["initialized"] is True
    assert (tmp_path / ".git").exists()

    # Re-detect: an existing repo is reused, not re-initialized.
    reuse = client.post("/api/git/init", json={"confirm": False}).json()
    assert reuse["action"] == "reuse"


# @HL-GIT-01 ----------------------------------------------------------------
def test_hl_git_01_panel_shows_status_history_and_branch(tmp_path, monkeypatch):
    service = _init_repo(tmp_path)
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "index.md").write_text("# Index\n")
    service.commit("docs: add index", paths=["knowledge/index.md"])
    (tmp_path / "knowledge" / "index.md").write_text("# Index\n\nchanged\n")

    client = _client(tmp_path, monkeypatch)
    status = client.get("/api/git/status").json()
    assert status["is_repo"] is True
    assert status["branch"]
    assert any(f["path"] == "knowledge/index.md" for f in status["changed_files"])

    diff = client.get("/api/git/diff", params={"path": "knowledge/index.md"}).json()
    assert "changed" in diff["diff"]

    log = client.get("/api/git/log").json()
    assert any(c["subject"] == "docs: add index" for c in log["commits"])


# @HL-GIT-03 ----------------------------------------------------------------
def test_hl_git_03_no_auto_commit_until_click_after_init(tmp_path, monkeypatch):
    service = _init_repo(tmp_path)
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "a.md").write_text("a\n")
    (tmp_path / "knowledge" / "b.md").write_text("b\n")

    client = _client(tmp_path, monkeypatch)
    suggestions = client.get("/api/git/suggest-commits").json()["suggestions"]
    assert suggestions
    assert all(s["message"] and s["files"] for s in suggestions)
    assert any(s["files"] == ["knowledge/a.md", "knowledge/b.md"] for s in suggestions)
    # Reviewing suggestions must NOT create a commit.
    assert client.get("/api/git/log").json()["commits"] == []

    # Only an explicit commit click records history.
    client.post("/api/git/commit", json={"message": "docs: add knowledge notes"})
    log = client.get("/api/git/log").json()["commits"]
    assert any(c["subject"] == "docs: add knowledge notes" for c in log)


# @HL-GIT-04 ----------------------------------------------------------------
def test_hl_git_04_auto_checkpoint_precedes_restore(tmp_path, monkeypatch):
    service = _init_repo(tmp_path)
    (tmp_path / "drafts").mkdir()
    intro = tmp_path / "drafts" / "intro.md"
    intro.write_text("original\n")
    service.commit("docs: add intro", paths=["drafts/intro.md"])
    intro.write_text("uncommitted edit\n")

    client = _client(tmp_path, monkeypatch)
    client.post("/api/settings", json={"workspace_preferences": {"auto_checkpoint": "true"}})
    result = client.post("/api/git/restore", json={"path": "drafts/intro.md", "ref": "HEAD"}).json()

    assert result["checkpoint"] is not None  # checkpoint captured prior state
    assert intro.read_text() == "original\n"  # restored
    subjects = [c["subject"] for c in client.get("/api/git/log").json()["commits"]]
    assert any(s.startswith("checkpoint:") for s in subjects)


def test_restore_always_checkpoints_even_without_auto_checkpoint_setting(tmp_path, monkeypatch):
    # The restore path has no UI-approval gate, so it must never silently drop
    # uncommitted work: a recovery checkpoint is captured regardless of the
    # auto_checkpoint preference (which is left at its default/off here).
    service = _init_repo(tmp_path)
    (tmp_path / "drafts").mkdir()
    intro = tmp_path / "drafts" / "intro.md"
    intro.write_text("original\n")
    service.commit("docs: add intro", paths=["drafts/intro.md"])
    intro.write_text("precious uncommitted edit\n")

    client = _client(tmp_path, monkeypatch)
    result = client.post("/api/git/restore", json={"path": "drafts/intro.md", "ref": "HEAD"}).json()

    assert result["checkpoint"] is not None  # the discarded edit was preserved
    assert intro.read_text() == "original\n"
    subjects = [c["subject"] for c in client.get("/api/git/log").json()["commits"]]
    assert any(s.startswith("checkpoint:") for s in subjects)


def test_restore_clean_tree_makes_no_checkpoint(tmp_path):
    # Nothing to lose: a restore on a genuinely clean working tree must not
    # fabricate an empty checkpoint commit. Exercised at the service level so the
    # app-data files the HTTP client writes into the repo root don't dirty it.
    service = _init_repo(tmp_path)
    (tmp_path / "drafts").mkdir()
    intro = tmp_path / "drafts" / "intro.md"
    intro.write_text("original\n")
    service.commit("chore: baseline", paths=None)  # stage everything -> clean tree
    assert service.status()["clean"] is True

    result = service.restore_previous_version("drafts/intro.md", ref="HEAD")

    assert result["checkpoint"] is None


# @HL-GIT-05 ----------------------------------------------------------------
def test_hl_git_05_destructive_reset_requires_ui_approval_not_console(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    client = _client(tmp_path, monkeypatch)

    denied = client.post("/api/git/destructive", json={"subcommand": "reset", "args": ["--hard"], "approved": False})
    assert denied.status_code == 403

    # The same reset cannot be invoked through the safe command console.
    console = client.post("/api/console/run", json={"command": "git reset --hard"}).json()
    assert console["status"] == "rejected"
    assert console["message"] == "command not allowed"
    assert console["spawned"] is False


def test_git_service_rejects_off_list_subcommand(tmp_path):
    service = GitService(tmp_path)
    service._run(["init"])
    try:
        service._run_read_only("push")
        raise AssertionError("expected GitError for off-list subcommand")
    except Exception as exc:  # noqa: BLE001
        assert "not allowed" in str(exc)


def test_commit_succeeds_without_ambient_git_identity(tmp_path, monkeypatch):
    # Fresh machine / bare CI runner: no global or system git identity at all.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    service = GitService(tmp_path)
    service._run(["init"])
    assert service._identity_flags() == ["-c", "user.name=HydraLab", "-c", "user.email=hydralab@localhost"]
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    result = service.commit("first checkpoint")
    assert result["committed"] is True
    author = service._run(["log", "-1", "--pretty=format:%an <%ae>"]).stdout.strip()
    assert author == "HydraLab <hydralab@localhost>"


def test_commit_preserves_configured_identity(tmp_path):
    service = GitService(tmp_path)
    service._run(["init"])
    service._run(["config", "user.email", "me@example.com"])
    service._run(["config", "user.name", "Me"])
    assert service._identity_flags() == []
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    service.commit("first")
    author = service._run(["log", "-1", "--pretty=format:%an <%ae>"]).stdout.strip()
    assert author == "Me <me@example.com>"
