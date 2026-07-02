import subprocess
from pathlib import Path

import pytest
import pytest_asyncio
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

from hydra.database.repository import Repository
from hydra.services.project_context import (
    ContextFileMemory,
    ensure_hydra_md,
    load_global_context,
    load_project_context,
)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def roots(tmp_path):
    project_root = tmp_path / "project"
    profile_root = tmp_path / "profile"
    project_root.mkdir()
    profile_root.mkdir()
    for name in ("SOUL.md", "USER.md", "MEMORY.md"):
        (profile_root / name).write_text(f"# {name}\n")
    (project_root / "HYDRA.md").write_text("# HYDRA.md\ndirection\n")
    return project_root, profile_root


# @HL-ASSIST-12 — global loaders accept an explicit profile id/root.
def test_hl_assist_12_global_loaders_profile_id_ready(roots):
    _, profile_root = roots
    files = load_global_context(profile_root, profile_id="researcher-a")
    names = {f.name for f in files}
    assert names == {"SOUL.md", "USER.md", "MEMORY.md"}
    assert all(f.recovery == "logs-only" and f.scope == "global" for f in files)


# @HL-ASSIST-13 — HYDRA.md loads as visible context and is Git-tracked.
def test_hl_assist_13_hydra_md_visible_and_git_tracked(tmp_path):
    project_root = tmp_path / "gitproj"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=project_root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=project_root, check=True)
    ensure_hydra_md(project_root)
    ctx = load_project_context(project_root)
    assert ctx.visible is True
    assert ctx.scope == "project"
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "HYDRA.md"], cwd=project_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    assert tracked.returncode == 0


# @HL-ASSIST-14 — critical fact writes immediately; normal fact batches. Both logged.
@pytest.mark.asyncio
async def test_hl_assist_14_hybrid_update_timing(session, roots):
    project_root, profile_root = roots
    memory = ContextFileMemory(session, project_root, profile_root)
    critical = await memory.record_update(
        file="USER.md", new_content="corresponding author", category="user_identity", project_id="p1"
    )
    normal = await memory.record_update(
        file="USER.md", new_content="prefers IEEE style", category="user_preference", project_id="p1"
    )
    assert critical.timing == "immediate"
    assert normal.timing == "batched"
    changes = await memory.list_changes(project_id="p1", file="USER.md")
    assert len(changes) == 2


# @HL-ASSIST-15 — a critical HYDRA.md edit creates an immediate checkpoint.
@pytest.mark.asyncio
async def test_hl_assist_15_critical_hydra_checkpoint(session, roots):
    project_root, profile_root = roots
    memory = ContextFileMemory(session, project_root, profile_root)
    result = await memory.record_update(
        file="HYDRA.md", new_content="# HYDRA.md\nnew direction\n", category="project_direction", project_id="p1"
    )
    assert result.written is True
    assert result.checkpoint_ref is not None
    assert memory.list_checkpoints("HYDRA.md")
    changes = await memory.list_changes(file="HYDRA.md")
    assert changes[0]["checkpoint_ref"] == result.checkpoint_ref


# @HL-ASSIST-15 — global file changes are logs-only, no checkpoint.
@pytest.mark.asyncio
async def test_hl_assist_15_global_logs_only(session, roots):
    project_root, profile_root = roots
    memory = ContextFileMemory(session, project_root, profile_root)
    result = await memory.record_update(file="MEMORY.md", new_content="a note", category="organization_update", project_id="p1")
    assert result.checkpoint_ref is None
    changes = await memory.list_changes(file="MEMORY.md")
    assert changes[0]["logs_only"] is True
    assert changes[0]["recovery"] == "logs-only"


# @HL-ASSIST-16 — condensing oversized HYDRA.md requires a recovery point first, no archive files.
@pytest.mark.asyncio
async def test_hl_assist_16_condense_requires_checkpoint_no_archive(session, roots):
    project_root, profile_root = roots
    big = "# HYDRA.md\n" + ("x" * (33 * 1024))
    (project_root / "HYDRA.md").write_text(big)
    memory = ContextFileMemory(session, project_root, profile_root)
    result = await memory.condense(file="HYDRA.md", condensed_content="# HYDRA.md\ncondensed\n", condense_threshold_kb=32)
    assert result.written is True
    assert result.checkpoint_ref is not None
    assert memory.list_checkpoints("HYDRA.md")  # recovery point exists
    # No separate archive file or archive folder was created.
    names = [p.name.lower() for p in project_root.rglob("*")]
    assert not any("archive" in n for n in names)


# @HL-ASSIST-17 — Memory/Context surface labels global logs-only and HYDRA git-backed.
@pytest.mark.asyncio
async def test_hl_assist_17_surface_labels(session, roots):
    project_root, profile_root = roots
    memory = ContextFileMemory(session, project_root, profile_root)
    await memory.record_update(file="MEMORY.md", new_content="x", category="organization_update", project_id="p1")
    await memory.record_update(file="HYDRA.md", new_content="# HYDRA.md\ny\n", category="project_direction", project_id="p1")
    changes = await memory.list_changes(project_id="p1")
    by_file = {c["file"]: c for c in changes}
    assert by_file["MEMORY.md"]["recovery"] == "logs-only"
    assert by_file["HYDRA.md"]["recovery"] == "git-checkpoint"
    assert by_file["HYDRA.md"]["checkpoint_ref"]


# @HL-ASSIST-18 / @HL-ASSIST-19 — candidate has fact/source/destination/confidence; routes to Review Inbox.
@pytest.mark.asyncio
async def test_hl_assist_18_19_memory_candidate_shape_and_routing(session, roots):
    project_root, profile_root = roots
    memory = ContextFileMemory(session, project_root, profile_root)
    candidate = await memory.route_memory_candidate(
        fact="the lab meets every Tuesday",
        destination="MEMORY.md",
        category="organization_update",
        confidence=0.7,
        source_ref="chat:123#m4",
        project_id="p1",
    )
    payload = candidate["payload"]
    assert payload["fact"] == "the lab meets every Tuesday"
    assert payload["source_ref"] == "chat:123#m4"
    assert payload["destination"] == "MEMORY.md"
    assert payload["confidence"] == 0.7
    items = await Repository(session).list_review_items("memory-candidate")
    assert any(i["id"] == candidate["id"] for i in items)


# @HL-ASSIST-20 — research conclusions never auto-promote; low-risk auto-promotes only when enabled.
@pytest.mark.asyncio
async def test_hl_assist_20_promotion_policy(session, roots):
    project_root, profile_root = roots
    memory = ContextFileMemory(session, project_root, profile_root)
    conclusion = await memory.promote_candidate(
        fact="method B outperforms method A",
        category="research_conclusion",
        destination="MEMORY.md",
        auto_promote_low_risk=True,
        project_id="p1",
    )
    assert conclusion["auto_promoted"] is False
    assert conclusion["review_item"] is not None

    tag = await memory.promote_candidate(
        fact="normalize tag ml -> machine-learning",
        category="tag_normalization",
        destination="MEMORY.md",
        auto_promote_low_risk=True,
        project_id="p1",
    )
    assert tag["auto_promoted"] is True
    assert tag["reversible"] is True

    tag_off = await memory.promote_candidate(
        fact="normalize tag nlp",
        category="tag_normalization",
        destination="MEMORY.md",
        auto_promote_low_risk=False,
        project_id="p1",
    )
    assert tag_off["auto_promoted"] is False


# @HL-ASSIST-17 — user can manually edit all four context files.
@pytest.mark.asyncio
async def test_manual_edit_all_context_files(session, roots):
    project_root, profile_root = roots
    memory = ContextFileMemory(session, project_root, profile_root)
    for name in ("SOUL.md", "USER.md", "MEMORY.md", "HYDRA.md"):
        result = await memory.manual_edit(file=name, new_content=f"# {name}\nedited\n", project_id="p1")
        assert result.written is True
    assert "edited" in (profile_root / "SOUL.md").read_text()
    assert "edited" in (project_root / "HYDRA.md").read_text()


# @HL-TRUST-03 — Memory/Context surface shows trust level of each change.
@pytest.mark.asyncio
async def test_hl_trust_03_provenance_in_surface(session, roots):
    project_root, profile_root = roots
    memory = ContextFileMemory(session, project_root, profile_root)
    await memory.manual_edit(file="HYDRA.md", new_content="# HYDRA.md\ntyped note\n", project_id="p1")
    await memory.record_update(
        file="HYDRA.md",
        new_content="untrusted",
        category="project_direction",
        provenance="untrusted-external",
        trust_level="untrusted-external",
        project_id="p1",
    )
    changes = await memory.list_changes(file="HYDRA.md")
    trusted = [c for c in changes if c["provenance"] == "user"]
    assert trusted and trusted[0]["trust_level"] == "trusted"
    # untrusted proposal was NOT written as a change to HYDRA.md (it routed to inbox)
    assert all(c["trust_level"] != "untrusted-external" for c in changes)
    assert "untrusted" not in (project_root / "HYDRA.md").read_text()
