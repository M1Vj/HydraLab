"""Phase-3 gated compute + sandbox execution safety tests (HL-SAFE-10..19).

Every test is offline and deterministic: trivial local scripts with ~1s
wall-clock caps, no network reachability and no heavy deps. The Seatbelt-backed
filesystem/network tests skip only if ``sandbox-exec`` is unavailable (it ships
with macOS, so they run for real here).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.compute.registry import BackendNotSelectableError, ComputeRegistry
from hydra.compute.sandbox import (
    LocalSandboxRunner,
    SandboxError,
    SandboxPolicy,
    SandboxProcess,
    build_default_policy,
    is_secret_name,
)
from hydra.compute import sandbox as sandbox_module
from hydra.database.repository import Repository
from hydra.experiments import models as run_status
from hydra.experiments.logs import RunLogStore, apply_cap
from hydra.experiments.runner import ExperimentRunner, RunLifecycleError
from hydra.experiments.search_adapter import SearchAdapter, SearchBudget

SEATBELT = shutil.which("sandbox-exec") is not None
needs_seatbelt = pytest.mark.skipif(not SEATBELT, reason="sandbox-exec unavailable; filesystem/network enforcement is best-effort")
PY = sys.executable


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine):
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session


def _policy(workspace: Path, **limits) -> SandboxPolicy:
    return build_default_policy(workspace_root=workspace, scratch_dir=workspace / "scratch", limits=limits)


def _git_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.dev"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)


# --- HL-SAFE-11: a run without a resolved policy never spawns -----------------
def test_no_policy_rejected_before_any_spawn(monkeypatch):
    spawned: list = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: spawned.append(a))
    with pytest.raises(SandboxError):
        LocalSandboxRunner(None)
    assert spawned == []


def test_argv_must_be_vector_not_shell_string(tmp_path):
    runner = LocalSandboxRunner(_policy(tmp_path, wall_clock_seconds=2))
    with pytest.raises(SandboxError):
        runner.run("echo hi; rm -rf /")  # a shell string is never accepted


# --- HL-SAFE-12: wall-clock timeout kills the whole group, no orphans --------
def test_wallclock_timeout_kills_process_group(tmp_path):
    runner = LocalSandboxRunner(_policy(tmp_path, wall_clock_seconds=1))
    process = runner.spawn([PY, "-c", "import time; time.sleep(30)"])
    pid = process.pid
    result = process.wait()
    shutil.rmtree(tmp_path / "scratch", ignore_errors=True)
    assert result.status == run_status.KILLED_TIMEOUT
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)  # no orphaned child survives


@needs_seatbelt
def test_network_denied_by_default(tmp_path):
    runner = LocalSandboxRunner(_policy(tmp_path, wall_clock_seconds=5))
    result = runner.run([PY, "-c", "import socket; socket.socket().connect(('127.0.0.1', 9)); print('CONNECTED')"])
    assert result.status == run_status.KILLED_NETWORK
    assert "CONNECTED" not in result.stdout
    # EPERM (not ECONNREFUSED) proves Seatbelt refused the syscall, not the kernel.
    assert "Operation not permitted" in result.stderr


@needs_seatbelt
def test_path_escape_denied(tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("classified")
    runner = LocalSandboxRunner(_policy(tmp_path, wall_clock_seconds=5))
    result = runner.run([PY, "-c", f"open({str(outside)!r}).read(); print('READ')"])
    assert result.status == run_status.KILLED_PATH_ESCAPE
    assert "READ" not in result.stdout


# --- HL-SAFE-15: cancel terminates the group and removes the scratch dir ------
def test_cancel_leaves_no_orphan_and_removes_scratch(tmp_path):
    policy = _policy(tmp_path, wall_clock_seconds=30)
    runner = LocalSandboxRunner(policy)
    process = runner.spawn([PY, "-c", "import time; time.sleep(30)"])
    pid = process.pid
    assert process.is_alive()
    assert policy.scratch_dir.exists()
    process.terminate()
    assert not process.is_alive()
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert not policy.scratch_dir.exists()

def test_windows_unconfined_requires_opt_in_and_spawn_uses_windows_process_group(tmp_path, monkeypatch):
    captured: dict = {}

    class FakePopen:
        pid = 4242

        def poll(self):
            return None

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakePopen()

    monkeypatch.setattr(sandbox_module.sys, "platform", "win32")
    monkeypatch.setattr(sandbox_module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(sandbox_module.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)
    monkeypatch.setattr(sandbox_module.subprocess, "Popen", fake_popen)

    policy = build_default_policy(workspace_root=tmp_path, scratch_dir=tmp_path / "scratch")
    assert policy.filesystem_network_enforcement == "unconfined"

    with pytest.raises(SandboxError, match="explicit opt-in"):
        LocalSandboxRunner(policy)

    process = LocalSandboxRunner(policy, accept_unconfined=True).spawn(["python", "-c", "pass"])

    assert process.pid == 4242
    assert captured["args"][0] == ["python", "-c", "pass"]
    assert captured["kwargs"]["creationflags"] == 512
    assert "preexec_fn" not in captured["kwargs"]
    assert "start_new_session" not in captured["kwargs"]

def test_windows_terminate_uses_taskkill_and_popen_kill(tmp_path, monkeypatch):
    calls: list[list[str]] = []

    class FakePopen:
        pid = 4343
        killed = False

        def poll(self):
            return None if not self.killed else -9

        def kill(self):
            self.killed = True

        def wait(self, timeout=None):
            return -9

    def fake_run(cmd, check=False, stdout=None, stderr=None):
        calls.append(cmd)

    monkeypatch.setattr(sandbox_module.sys, "platform", "win32")
    monkeypatch.setattr(sandbox_module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(sandbox_module.subprocess, "run", fake_run)

    policy = build_default_policy(workspace_root=tmp_path, scratch_dir=tmp_path / "scratch")
    policy.scratch_dir.mkdir(parents=True)
    popen = FakePopen()
    process = SandboxProcess(popen, policy=policy, started=0)

    process.terminate()

    assert calls == [["taskkill", "/T", "/F", "/PID", "4343"]]
    assert popen.killed is True
    assert not policy.scratch_dir.exists()

def test_linux_bwrap_policy_wraps_argv_with_network_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_module.sys, "platform", "linux")
    monkeypatch.setattr(sandbox_module, "_bwrap_usable", lambda: True)

    policy = build_default_policy(workspace_root=tmp_path, scratch_dir=tmp_path / "scratch", network="none")
    assert policy.filesystem_network_enforcement == "bwrap"

    wrapped = LocalSandboxRunner(policy)._wrap(["python", "train.py"])

    assert wrapped[:10] == [
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--bind",
        str(policy.scratch_dir),
        str(policy.scratch_dir),
        "--chdir",
    ]
    assert wrapped[10] == str(policy.scratch_dir)
    assert "--unshare-net" in wrapped
    assert wrapped[-2:] == ["python", "train.py"]

def test_linux_without_bwrap_is_best_effort(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_module.sys, "platform", "linux")
    monkeypatch.setattr(sandbox_module, "_bwrap_usable", lambda: False)

    policy = build_default_policy(workspace_root=tmp_path, scratch_dir=tmp_path / "scratch")

    assert policy.filesystem_network_enforcement == "best_effort"

def test_linux_bwrap_present_but_unusable_degrades_to_best_effort(tmp_path, monkeypatch):
    # bwrap is on PATH but cannot create namespaces (containers / hardened kernels)
    monkeypatch.setattr(sandbox_module.sys, "platform", "linux")
    monkeypatch.setattr(sandbox_module, "_BWRAP_USABLE", None, raising=False)
    monkeypatch.setattr(sandbox_module.shutil, "which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)

    class _Failed:
        returncode = 1

    monkeypatch.setattr(sandbox_module.subprocess, "run", lambda *a, **k: _Failed())

    policy = build_default_policy(workspace_root=tmp_path, scratch_dir=tmp_path / "scratch")
    assert policy.filesystem_network_enforcement == "best_effort"


# --- HL-SAFE-19: provider secrets never enter the sandbox env or logs ---------
def test_secret_env_excluded_from_child(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-should-never-appear")
    monkeypatch.setenv("MY_SESSION_TOKEN", "tok-should-never-appear")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    policy = _policy(tmp_path, wall_clock_seconds=5)
    env = policy.child_env()
    assert "OPENAI_API_KEY" not in env
    assert "MY_SESSION_TOKEN" not in env
    result = LocalSandboxRunner(policy).run([PY, "-c", "import os,json; print(json.dumps(dict(os.environ)))"])
    assert "sk-live-should-never-appear" not in result.stdout
    assert "tok-should-never-appear" not in result.stdout


def test_is_secret_name_matrix():
    assert is_secret_name("OPENAI_API_KEY")
    assert is_secret_name("ANTHROPIC_API_KEY")
    assert is_secret_name("AWS_SECRET_ACCESS_KEY")
    assert is_secret_name("some_token")
    assert not is_secret_name("PATH")
    assert not is_secret_name("LANG")


# --- HL-SAFE-14: bounded logs keep the cap plus an explicit marker ------------
def test_apply_cap_marks_truncation():
    outcome = apply_cap("x" * 4_194_304, 1_048_576)
    assert outcome.truncated
    assert outcome.omitted == 3_145_728
    assert outcome.content.endswith("[truncated: 3145728 bytes omitted]")
    assert outcome.content.startswith("x" * 1_048_576)


@pytest.mark.asyncio
async def test_run_logs_are_bounded_and_keyed(session):
    store = RunLogStore(session, cap_bytes=1_048_576)
    await store.append_stream("grid-search-01", "stdout", "y" * 4_194_304)
    rows = await store.read("grid-search-01")
    assert rows and all(row.run_id == "grid-search-01" for row in rows)
    stdout_row = next(row for row in rows if row.stream == "stdout")
    assert stdout_row.truncated
    assert stdout_row.content.endswith("[truncated: 3145728 bytes omitted]")


# --- HL-SAFE-10: registry only offers enabled, registered backends -----------
@pytest.mark.asyncio
async def test_registry_seeds_local_and_rejects_disabled(session):
    registry = ComputeRegistry(session)
    local = await registry.ensure_seeded()
    assert local.kind == "local_sandbox" and local.enabled
    resolved = await registry.resolve(local.id)
    assert not resolved.is_cloud
    disabled = await registry.register(kind="cloud", display_name="modal-a100", enabled=False)
    with pytest.raises(BackendNotSelectableError):
        await registry.resolve(disabled.id)
    with pytest.raises(BackendNotSelectableError):
        await registry.resolve("does-not-exist")


@pytest.mark.asyncio
async def test_disabled_backend_rejected_by_run_path(session, tmp_path):
    registry = ComputeRegistry(session)
    disabled = await registry.register(kind="cloud", display_name="modal-a100", enabled=False)
    runner = ExperimentRunner(session, workspace_root=tmp_path)
    proposal = await runner.create_run(
        project_id="p1", backend_id=disabled.id, config={"argv": [PY, "-c", "pass"]}, label="vit-finetune"
    )
    assert proposal.run.status == run_status.STATUS_AWAITING_APPROVAL
    assert "backend disabled" in proposal.reason


# --- HL-SAFE-17: cloud requires a budget + spend approval --------------------
@pytest.mark.asyncio
async def test_cloud_run_without_budget_rejected(session, tmp_path):
    registry = ComputeRegistry(session)
    cloud = await registry.register(kind="cloud", display_name="modal", enabled=True)
    runner = ExperimentRunner(session, workspace_root=tmp_path)
    await runner.gate.enable_execution("p1")
    proposal = await runner.create_run(
        project_id="p1", backend_id=cloud.id, config={"argv": [PY, "-c", "pass"]}, label="cloud-train"
    )
    assert proposal.run.status == run_status.STATUS_AWAITING_APPROVAL
    assert "budget" in proposal.reason.lower()
    # No approval was requested -> nothing to start; the run cannot proceed.
    assert proposal.approval_id is None


# --- HL-SAFE-17: an unapproved run never starts (no auto-trigger) -------------
@pytest.mark.asyncio
async def test_unapproved_run_stays_awaiting_approval(session, tmp_path):
    _git_repo(tmp_path)
    registry = ComputeRegistry(session)
    local = await registry.ensure_seeded()
    runner = ExperimentRunner(session, workspace_root=tmp_path)
    await runner.gate.enable_execution("p1")
    proposal = await runner.create_run(
        project_id="p1", backend_id=local.id, config={"argv": [PY, "-c", "print('hi')"]}, label="baseline"
    )
    assert proposal.approval_id  # a pending approval exists, but is NOT approved
    with pytest.raises(RunLifecycleError):
        await runner.start_run(proposal.run.id)
    refreshed = await runner._get(proposal.run.id)
    assert refreshed.status == run_status.STATUS_AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_execution_disabled_blocks_start(session, tmp_path):
    _git_repo(tmp_path)
    registry = ComputeRegistry(session)
    local = await registry.ensure_seeded()
    runner = ExperimentRunner(session, workspace_root=tmp_path)
    # execution_enabled defaults OFF -> even an approved run cannot start.
    proposal = await runner.create_run(project_id="p1", backend_id=local.id, config={"argv": [PY, "-c", "pass"]})
    await runner.approve_run(proposal.run.id)
    with pytest.raises(RunLifecycleError):
        await runner.start_run(proposal.run.id)


# --- HL-SAFE-18: untrusted provenance routes to the Review Inbox --------------
@pytest.mark.asyncio
async def test_untrusted_origin_routes_to_review_inbox(session, tmp_path):
    registry = ComputeRegistry(session)
    local = await registry.ensure_seeded()
    runner = ExperimentRunner(session, workspace_root=tmp_path)
    await runner.gate.enable_execution("p1")
    proposal = await runner.create_run(
        project_id="p1",
        backend_id=local.id,
        config={"argv": [PY, "-c", "print('hi')"]},
        label="train.py",
        trust_origin="untrusted-external",
        justification_trust="untrusted-external",
    )
    assert proposal.review_item_id is not None
    assert proposal.approval_id is None
    assert proposal.run.status == run_status.STATUS_AWAITING_APPROVAL
    items = await Repository(session).list_review_items("agent-stage-proposal")
    assert any(item["id"] == proposal.review_item_id for item in items)
    with pytest.raises(RunLifecycleError):
        await runner.start_run(proposal.run.id)  # review-inbox run never auto-starts


# --- HL-SAFE-13/16: happy path runs, checkpoints, and rolls back -------------
@pytest.mark.asyncio
async def test_approved_run_succeeds_and_records_outcome(session, tmp_path):
    _git_repo(tmp_path)
    (tmp_path / "seed.txt").write_text("v1")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=tmp_path, check=True)
    registry = ComputeRegistry(session)
    local = await registry.ensure_seeded()
    runner = ExperimentRunner(session, workspace_root=tmp_path)
    await runner.gate.enable_execution("p1")
    proposal = await runner.create_run(
        project_id="p1",
        backend_id=local.id,
        config={"argv": [PY, "-c", "print('##HYDRA_METRIC {\"accuracy\": 0.91}')"]},
        label="baseline-train",
    )
    await runner.approve_run(proposal.run.id)
    run = await runner.start_run(proposal.run.id)
    assert run.status == run_status.STATUS_SUCCEEDED
    assert run.checkpoint_ref
    assert '"accuracy": 0.91' in run.metrics_json


@pytest.mark.asyncio
async def test_rollback_restores_pre_run_checkpoint(session, tmp_path):
    _git_repo(tmp_path)
    tracked = tmp_path / "writing" / "manuscript.md"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("original")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    registry = ComputeRegistry(session)
    local = await registry.ensure_seeded()
    runner = ExperimentRunner(session, workspace_root=tmp_path)
    await runner.gate.enable_execution("p1")
    proposal = await runner.create_run(project_id="p1", backend_id=local.id, config={"argv": [PY, "-c", "pass"]})
    await runner.approve_run(proposal.run.id)
    run = await runner.start_run(proposal.run.id)
    assert run.checkpoint_ref
    # Simulate post-run workspace drift, then roll back to the pre-run checkpoint.
    tracked.write_text("corrupted by a failed run")
    await runner.rollback_run(run.id)
    assert tracked.read_text() == "original"


# --- HL-SAFE-13/17: the bounded search adapter ranks within budget -----------
@pytest.mark.asyncio
async def test_search_adapter_ranks_within_budget(session, tmp_path):
    _git_repo(tmp_path)
    registry = ComputeRegistry(session)
    local = await registry.ensure_seeded()
    runner = ExperimentRunner(session, workspace_root=tmp_path)
    await runner.gate.enable_execution("p1")
    adapter = SearchAdapter(runner)

    def argv_builder(config: dict) -> list[str]:
        score = float(config["param"])
        return [PY, "-c", f"print('##HYDRA_METRIC {{\"score\": {score}}}')"]

    budget = SearchBudget(max_candidates=3, metric_key="score", direction="max")
    result = await adapter.run_search(
        project_id="p1", backend_id=local.id, base_config={"seed": 0.2}, budget=budget, argv_builder=argv_builder
    )
    assert result.submitted == 3
    assert result.best is not None
    metrics = [c.metric for c in result.ranked if c.metric is not None]
    assert metrics == sorted(metrics, reverse=True)  # ranked best-first


# --- audit ledger records every lifecycle transition -------------------------
@pytest.mark.asyncio
async def test_audit_ledger_records_run_lifecycle(session, tmp_path):
    _git_repo(tmp_path)
    registry = ComputeRegistry(session)
    local = await registry.ensure_seeded()
    runner = ExperimentRunner(session, workspace_root=tmp_path)
    await runner.gate.enable_execution("p1")
    proposal = await runner.create_run(project_id="p1", backend_id=local.id, config={"argv": [PY, "-c", "pass"]})
    await runner.approve_run(proposal.run.id)
    await runner.start_run(proposal.run.id)
    entries = await runner.audit.list(project_id="p1", run_id=proposal.run.id)
    assert any(e.approval_state == "applied" for e in entries)
