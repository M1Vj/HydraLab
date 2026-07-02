import sqlite3
from pathlib import Path

import pytest
import pytest_asyncio
from sqlmodel import SQLModel, select
from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from alembic import command
from alembic.config import Config

from hydra.database import repository as repository_module
from hydra.database.models import (
    Annotation,
    Claim,
    ConversionWarning,
    EvidenceLink,
    ExtractedImage,
    IngestionArtifact,
    IngestionJob,
    IndexQueueItem,
    KgEdge,
    LexicalIndexEntry,
    Note,
    NoteLink,
    SchemaVersion,
    Source,
    SourceTombstone,
    ReviewItem,
    Workspace,
)
from hydra.database.crud import CRUD
from hydra.database.repository import Repository
from hydra.storage.app_data import init_app_data
from hydra.storage.migration import migrate_legacy_hydra_project
from hydra.storage.project import (
    create_project,
    ensure_feature_folders,
    evaluate_git_init,
    is_git_tracked,
    reindex_notes_from_canonical_files,
)
from hydra.storage.sidecar import resolve_sidecar_conflict

@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def session(engine):
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_maker() as session:
        yield session


def test_hl_core_01_project_init_writes_only_core_tree_and_on_demand_paper_folders(tmp_path):
    project = create_project(tmp_path / "Transformer Survey", "Transformer Survey", git_enabled=False)

    expected = {
        "README.md",
        "project.yaml",
        "HYDRA.md",
        "sources",
        "knowledge",
        "work",
        "writing",
        "outputs",
        ".hydralab",
    }
    assert {path.name for path in project.root.iterdir()} == expected
    assert (project.root / ".hydralab" / "hydralab.db").exists()
    assert not (project.root / "sources" / "papers" / "pdf").exists()
    assert not (project.root / "outputs" / "manuscripts").exists()

    ensure_feature_folders(project.root, "paper")
    assert (project.root / "sources" / "papers" / "pdf").is_dir()
    assert (project.root / "sources" / "papers" / "metadata").is_dir()
    assert (project.root / "sources" / "papers" / "annotations").is_dir()
    ensure_feature_folders(project.root, "paper")


def test_hl_core_01_project_init_rerun_preserves_project_yaml_unknown_keys(tmp_path):
    from hydra.settings.project_config import load_project_config, save_project_config

    project = create_project(tmp_path / "Transformer Survey", "Transformer Survey", git_enabled=False)
    config_path = project.root / "project.yaml"
    config = load_project_config(config_path).data
    config["future_hydralab_key"] = {"keep": True}
    config["custom_metadata"]["local_note"] = "preserve me"
    save_project_config(config_path, config)

    rerun = create_project(project.root, "Transformer Survey", git_enabled=False)
    reloaded = load_project_config(config_path).data

    assert rerun.created is False
    assert reloaded["project_id"] == project.project_id
    assert reloaded["future_hydralab_key"] == {"keep": True}
    assert reloaded["custom_metadata"]["local_note"] == "preserve me"


def test_hl_core_02_git_init_detection_and_hydra_tracked(tmp_path):
    existing = tmp_path / "Existing"
    existing.mkdir()

    decision = evaluate_git_init(existing, created_by_hydralab=False, git_enabled=True)
    assert decision.action == "ask"
    assert not (existing / ".git").exists()

    project = create_project(tmp_path / "New Project", "New Project", git_enabled=True)
    assert (project.root / ".git").exists()
    assert is_git_tracked(project.root, "HYDRA.md")
    gitignore = (project.root / ".gitignore").read_text() if (project.root / ".gitignore").exists() else ""
    assert "HYDRA.md" not in gitignore

    reused = evaluate_git_init(project.root, created_by_hydralab=False, git_enabled=True)
    assert reused.action == "reuse"

    empty_existing = tmp_path / "Empty Existing"
    empty_existing.mkdir()
    create_project(empty_existing, "Empty Existing", git_enabled=True)
    assert not (empty_existing / ".git").exists()


def test_hl_core_03_app_data_profile_is_global_and_project_free(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRALAB_APP_DATA_ROOT", str(tmp_path / "app-data"))
    project_root = tmp_path / "project"
    project_root.mkdir()

    profile = init_app_data()

    assert profile.profile_id == "default"
    assert (profile.profile_root / "SOUL.md").exists()
    assert (profile.profile_root / "USER.md").exists()
    assert (profile.profile_root / "MEMORY.md").exists()
    assert not (profile.app_root / "HYDRA.md").exists()
    assert not (project_root / "SOUL.md").exists()
    assert profile.path_for_profile("future-profile").name == "future-profile"


@pytest.mark.asyncio
async def test_hl_core_04_section_31_tables_have_stable_ids_trust_origin_and_rebuildable_notes(session: AsyncSession, tmp_path):
    repo = Repository(session)
    created = await repo.create_section31_entity("note", project_id="p1", path="work/notes/a.md", title="A")
    fetched = await repo.get_section31_entity("note", created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["trust_origin"] == "user"

    note_path = tmp_path / "work" / "notes" / "self-attention.md"
    note_path.parent.mkdir(parents=True)
    note_path.write_text("---\nnote_id: n-7f3a9c\ntitle: Self-attention scaling intuition\n---\n\nBody")
    session.add(Note(id="n-7f3a9c", workspace_id="p1", title="drop me", body="", relative_path="work/notes/self-attention.md"))
    await session.commit()
    await session.delete(await session.get(Note, "n-7f3a9c"))
    await session.commit()

    rebuilt = await reindex_notes_from_canonical_files(tmp_path, session, project_id="p1")
    assert rebuilt == ["n-7f3a9c"]
    restored = await session.get(Note, "n-7f3a9c")
    assert restored is not None
    assert restored.title == "Self-attention scaling intuition"


@pytest.mark.asyncio
async def test_hl_core_06_project_yaml_migrates_to_current_schema(tmp_path):
    from hydra.settings.project_config import load_project_config

    path = tmp_path / "project.yaml"
    path.write_text(
        "schema_version: 1\n"
        "project_id: p-transformer\n"
        "name: Transformer Survey\n"
        "description: Old schema\n"
        "created_at: 2026-01-01T00:00:00Z\n"
        "updated_at: 2026-01-01T00:00:00Z\n"
        "hydralab_version: 0.1.0\n"
        "project_type: literature_review\n"
        "domain: computer_science\n"
        "default_citation_style: apa\n"
        "folders: {}\n"
        "features: {}\n"
        "privacy: {}\n"
        "browser: {}\n"
        "sources: {}\n"
        "writing: {}\n"
        "git: {}\n"
        "custom_metadata: {}\n"
    )

    config = load_project_config(path)

    assert config.data["schema_version"] == 2
    assert config.data["project_id"] == "p-transformer"
    assert config.data["name"] == "Transformer Survey"
    assert config.data["default_citation_style"] == "apa"
    assert config.data["default_manuscript_profile"] == "default"


@pytest.mark.asyncio
async def test_hl_core_07_project_create_is_offline_and_records_schema_version(tmp_path, monkeypatch):
    def fail_network(*args, **kwargs):
        raise AssertionError("network should not be used for project creation")

    monkeypatch.setattr("socket.create_connection", fail_network)
    project = create_project(tmp_path / "Transformer Survey", "Transformer Survey", git_enabled=False)
    assert project.root.exists()

    conn = sqlite3.connect(project.root / ".hydralab" / "hydralab.db")
    try:
        version = conn.execute("select version from schema_versions where component = 'database'").fetchone()
    finally:
        conn.close()
    assert version == ("2026.01.02",)


@pytest.mark.asyncio
async def test_hl_refint_01_merge_sources_repoints_evidence_and_leaves_zero_dangling(session: AsyncSession):
    repo = Repository(session)
    survivor = Source(id="00000000-0000-0000-0000-000000000001", title="Attention", doi="10.48550/arXiv.1706.03762")
    duplicate = Source(id="00000000-0000-0000-0000-000000000002", title="Attention duplicate", doi="10.48550/arXiv.1706.03762")
    claim = Claim(id="claim-1", text="Transformers use attention.")
    evidence = EvidenceLink(claim_id=claim.id, source_id=duplicate.id, passage="quote", support="supported", confidence=0.9, review_status="accepted")
    session.add_all([survivor, duplicate, claim, evidence])
    await session.commit()

    result = await repo.merge_sources([survivor.id, duplicate.id], reason="exact_identifier")

    assert result["survivor_id"] == survivor.id
    assert (await session.get(EvidenceLink, evidence.id)).source_id == survivor.id
    assert await session.get(SourceTombstone, duplicate.id)
    assert await repo.count_references_to_source(duplicate.id) == 0


def test_hl_refint_01_source_reference_registry_covers_model_source_foreign_keys():
    discovered = set()
    for table in SQLModel.metadata.tables.values():
        for column in table.columns:
            for foreign_key in column.foreign_keys:
                if foreign_key.column.table.name == "sources" and foreign_key.column.name == "id":
                    discovered.add((table.name, column.name))

    assert discovered
    assert discovered <= repository_module.SOURCE_DIRECT_REFERENCE_COLUMNS


def test_alembic_upgrade_head_schema_matches_sqlmodel_metadata(tmp_path: Path):
    db_path = tmp_path / "alembic-head.db"
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    try:
        actual = _schema_signature(inspector)
        expected = _metadata_signature()
    finally:
        engine.dispose()

    assert actual == expected


def _schema_signature(inspector):
    signature = {}
    for table_name in sorted(SQLModel.metadata.tables):
        columns = inspector.get_columns(table_name)
        pk = set(inspector.get_pk_constraint(table_name).get("constrained_columns") or [])
        fks = {
            (fk["constrained_columns"][0], fk["referred_table"], fk["referred_columns"][0])
            for fk in inspector.get_foreign_keys(table_name)
            if fk.get("constrained_columns") and fk.get("referred_columns")
        }
        signature[table_name] = {
            column["name"]: {
                "primary_key": column["name"] in pk,
                "nullable": bool(column["nullable"]) and column["name"] not in pk,
                "foreign_keys": sorted(fk for fk in fks if fk[0] == column["name"]),
            }
            for column in columns
        }
    return signature


def _metadata_signature():
    signature = {}
    for table_name, table in sorted(SQLModel.metadata.tables.items()):
        signature[table_name] = {
            column.name: {
                "primary_key": bool(column.primary_key),
                "nullable": bool(column.nullable) and not column.primary_key,
                "foreign_keys": sorted((column.name, fk.column.table.name, fk.column.name) for fk in column.foreign_keys),
            }
            for column in table.columns
        }
    return signature


def test_hl_refint_01_source_reference_registry_covers_source_polymorphic_pairs():
    conventions = [
        ("location_type", "location_id"),
        ("source_type", "source_id"),
        ("target_type", "target_id"),
        ("target_type", "target_id_or_path"),
        ("src_type", "src_id"),
        ("dst_type", "dst_id_or_path"),
        ("origin_type", "origin_id"),
    ]
    discovered = set()
    for table in SQLModel.metadata.tables.values():
        column_names = set(table.columns.keys())
        for type_column, id_column in conventions:
            if type_column in column_names and id_column in column_names:
                discovered.add((table.name, type_column, "source", id_column))

    assert discovered
    assert discovered <= repository_module.SOURCE_POLYMORPHIC_REFERENCE_COLUMNS


@pytest.mark.asyncio
async def test_hl_refint_01_merge_sources_repoints_all_source_references(session: AsyncSession):
    repo = Repository(session)
    survivor = Source(id="00000000-0000-0000-0000-000000000011", title="Attention", doi="10.48550/arXiv.1706.03762")
    duplicate = Source(id="00000000-0000-0000-0000-000000000012", title="Attention duplicate", doi="10.48550/arXiv.1706.03762")
    note = Note(id="note-1", title="Source note", source_id=duplicate.id)
    note_link_target = NoteLink(source_id=note.id, source_type="note", target_source_id=duplicate.id, raw_target_name="Attention")
    note_link_source = NoteLink(source_id=duplicate.id, source_type="source", raw_target_name="Generated from source")
    kg_src = KgEdge(project_id="p1", src_id=duplicate.id, src_type="source", dst_id_or_path=note.id, dst_type="note")
    kg_dst = KgEdge(project_id="p1", src_id=note.id, src_type="note", dst_id_or_path=duplicate.id, dst_type="source")
    review_origin = ReviewItem(item_type="source-review", title="origin", origin_type="source", origin_id=duplicate.id)
    review_target = ReviewItem(item_type="source-review", title="target", target_type="source", target_id=duplicate.id)
    queue_item = IndexQueueItem(project_id="p1", target_type="source", target_id_or_path=duplicate.id)
    lexical_entry = LexicalIndexEntry(source_id=duplicate.id, chunk_id="chunk-1")
    ingestion_job = IngestionJob(source_id=duplicate.id, source_path="sources/paper.pdf")
    ingestion_artifact = IngestionArtifact(source_id=duplicate.id, engine="pypdf", kind="text", path="sources/paper.md")
    extracted_image = ExtractedImage(source_id=duplicate.id, path="sources/images/fig1.png")
    conversion_warning = ConversionWarning(source_id=duplicate.id, code="warn", message="warning")
    session.add_all(
        [
            survivor,
            duplicate,
            note,
            note_link_target,
            note_link_source,
            kg_src,
            kg_dst,
            review_origin,
            review_target,
            queue_item,
            lexical_entry,
            ingestion_job,
            ingestion_artifact,
            extracted_image,
            conversion_warning,
        ]
    )
    await session.commit()

    result = await repo.merge_sources([survivor.id, duplicate.id], reason="exact_identifier")

    assert result["survivor_id"] == survivor.id
    assert (await session.get(Note, note.id)).source_id == survivor.id
    assert (await session.get(NoteLink, note_link_target.id)).target_source_id == survivor.id
    assert (await session.get(NoteLink, note_link_source.id)).source_id == survivor.id
    assert (await session.get(KgEdge, kg_src.id)).src_id == survivor.id
    assert (await session.get(KgEdge, kg_dst.id)).dst_id_or_path == survivor.id
    assert (await session.get(ReviewItem, review_origin.id)).origin_id == survivor.id
    assert (await session.get(ReviewItem, review_target.id)).target_id == survivor.id
    assert (await session.get(IndexQueueItem, queue_item.id)).target_id_or_path == survivor.id
    assert (await session.get(LexicalIndexEntry, lexical_entry.id)).source_id == survivor.id
    assert (await session.get(IngestionJob, ingestion_job.id)).source_id == survivor.id
    assert (await session.get(IngestionArtifact, ingestion_artifact.id)).source_id == survivor.id
    assert (await session.get(ExtractedImage, extracted_image.id)).source_id == survivor.id
    assert (await session.get(ConversionWarning, conversion_warning.id)).source_id == survivor.id
    assert await repo.count_references_to_source(duplicate.id) == 0


@pytest.mark.asyncio
async def test_hl_refint_01_merge_rolls_back_when_zero_dangling_gate_finds_missed_reference(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = Repository(session)
    survivor = Source(id="00000000-0000-0000-0000-000000000021", title="Attention", doi="10.48550/arXiv.1706.03762")
    duplicate = Source(id="00000000-0000-0000-0000-000000000022", title="Attention duplicate", doi="10.48550/arXiv.1706.03762")
    note = Note(id="note-missed", title="Missed source note", source_id=duplicate.id)
    duplicate_id = duplicate.id
    note_id = note.id
    session.add_all([survivor, duplicate, note])
    await session.commit()

    async def missed_repoint(_old_id: str, _survivor_id: str) -> None:
        return None

    monkeypatch.setattr(repo, "_repoint_source_references", missed_repoint)

    with pytest.raises(RuntimeError, match="dangling references remain"):
        await repo.merge_sources([survivor.id, duplicate.id], reason="exact_identifier")

    assert (await session.get(Source, duplicate_id)).trashed is False
    assert (await session.get(Note, note_id)).source_id == duplicate_id


@pytest.mark.asyncio
async def test_hl_refint_02_trash_and_restore_referenced_source_preserves_links(session: AsyncSession):
    repo = Repository(session)
    source = Source(id="source-1", title="Attention Is All You Need")
    claim = Claim(id="claim-1", text="Attention works.", location_type="source", location_id=source.id)
    annotation = Annotation(sidecar_record_id="ann-1", source_id=source.id, page=1, text="quote")
    session.add_all([source, claim, annotation])
    await session.commit()

    trashed = await repo.trash_source(source.id, confirmed=True)
    assert trashed["dependent_counts"]["claims"] == 1
    assert trashed["dependent_counts"]["annotations"] == 1
    assert (await session.get(Source, source.id)).trashed is True
    assert (await session.get(Claim, claim.id)).link_state == "target_trashed"
    assert (await session.get(Annotation, annotation.sidecar_record_id)).link_state == "target_trashed"
    assert await repo.list_review_items(item_type="broken-link")

    restored = await repo.restore_source(source.id)
    assert restored["restored"] is True
    assert (await session.get(Claim, claim.id)).location_id == source.id
    assert (await session.get(Claim, claim.id)).link_state == "live"
    assert (await session.get(Annotation, annotation.sidecar_record_id)).source_id == source.id
    assert (await session.get(Annotation, annotation.sidecar_record_id)).link_state == "live"


def test_hl_refint_03_sidecar_conflict_uses_rev_and_content_hash_not_mtime():
    older_mtime_winner = {
        "sidecar_record_id": "a1b2c3",
        "rev": 5,
        "content_hash": "hash-new",
        "mtime": 1,
    }
    loser = {
        "sidecar_record_id": "a1b2c3",
        "rev": 4,
        "content_hash": "hash-old",
        "mtime": 999,
    }

    resolved = resolve_sidecar_conflict(loser, older_mtime_winner)

    assert resolved.record["rev"] == 5
    assert resolved.used_mtime is False


def test_hl_refint_04_migrate_legacy_hydra_project_rewrites_refs_and_leaves_original_intact(tmp_path):
    legacy_dir = tmp_path / ".hydra"
    legacy_dir.mkdir()
    legacy_db = legacy_dir / "hydra.db"
    conn = sqlite3.connect(legacy_db)
    conn.executescript(
        """
        create table sources (id text primary key, title text);
        create table claims (id text primary key, location_type text, location_id text, text text);
        create table evidence_links (id text primary key, claim_id text, source_id text, passage text);
        create table annotations (sidecar_record_id text primary key, source_id text, text text);
        insert into sources values ('s-1', 'Attention');
        insert into claims values ('c-1', 'source', 's-1', 'claim');
        insert into evidence_links values ('e-1', 'c-1', 's-1', 'quote');
        insert into annotations values ('a-1', 's-1', 'note');
        """
    )
    conn.commit()
    conn.close()

    report = migrate_legacy_hydra_project(tmp_path)

    assert report.zero_dangling is True
    assert report.id_map["sources"]["s-1"] == "s-1"
    assert legacy_db.exists()
    migrated = sqlite3.connect(tmp_path / ".hydralab" / "hydralab.db")
    try:
        assert migrated.execute("select source_id from evidence_links where id = 'e-1'").fetchone() == ("s-1",)
    finally:
        migrated.close()


@pytest.mark.asyncio
async def test_hl_core_09_version_mismatch_flags_reindex_without_new_source_id(session: AsyncSession):
    source = Source(id="s-1706-03762", title="Attention Is All You Need")
    entry = LexicalIndexEntry(
        id="idx-1",
        source_id=source.id,
        chunk_id="chunk-1",
        locator="p1",
        text="attention",
        extraction_version=1,
        index_version=1,
    )
    session.add_all([source, entry])
    await session.commit()

    repo = Repository(session)
    mismatches = await repo.evaluate_index_versions(current_index_version=2, current_extraction_version=1)

    assert mismatches == [{"source_id": "s-1706-03762", "reason": "index_version"}]
    assert (await session.get(Source, "s-1706-03762")).id == "s-1706-03762"

@pytest.mark.asyncio
async def test_crud_workspace(session: AsyncSession):
    crud = CRUD(session)
    ws = await crud.create_workspace("Test Workspace")
    assert ws.id is not None
    assert ws.name == "Test Workspace"

    fetched = await crud.get_workspace(ws.id)
    assert fetched is not None
    assert fetched.name == "Test Workspace"

    workspaces = await crud.get_workspaces()
    assert len(workspaces) == 1

@pytest.mark.asyncio
async def test_crud_conversation(session: AsyncSession):
    crud = CRUD(session)
    ws = await crud.create_workspace("WS for Conv")
    conv = await crud.create_conversation(ws.id, "Test Conv")
    
    assert conv.id is not None
    assert conv.workspace_id == ws.id
    
    convs = await crud.get_conversations(ws.id)
    assert len(convs) == 1
    assert convs[0].title == "Test Conv"

@pytest.mark.asyncio
async def test_crud_task(session: AsyncSession):
    crud = CRUD(session)
    ws = await crud.create_workspace("WS for Task")
    task = await crud.create_task(
        workspace_id=ws.id,
        title="Test Task",
        column_name="to_do",
        detail="Detail of task",
        progress=10,
        phase_indicator="retrieving sources",
        position=2
    )
    
    assert task.id is not None
    assert task.column_name == "to_do"
    assert task.progress == 10
    assert task.phase_indicator == "retrieving sources"
    assert task.position == 2
    
    updated = await crud.update_task(task.id, progress=50, column_name="in_progress", phase_indicator="summarising papers", position=1)
    assert updated.progress == 50
    assert updated.column_name == "in_progress"
    assert updated.phase_indicator == "summarising papers"
    assert updated.position == 1
    
    # Test Ordering
    task2 = await crud.create_task(
        workspace_id=ws.id,
        title="Second Task",
        column_name="to_do",
        detail="Another one",
        progress=0,
        phase_indicator="",
        position=0
    )
    
    tasks = await crud.get_tasks(ws.id)
    assert len(tasks) == 2
    # Since position 0 < 1, task2 should come first
    assert tasks[0].id == task2.id
    assert tasks[1].id == task.id

    # Test Deletion
    deleted = await crud.delete_task(task2.id)
    assert deleted is True
    
    tasks_after_delete = await crud.get_tasks(ws.id)
    assert len(tasks_after_delete) == 1
    assert tasks_after_delete[0].id == task.id
