from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import Annotation, Claim, Note, ReviewItem, Source
from hydra.services.annotations.index import AnnotationIndexer
from hydra.services.annotations.sidecar import (
    annotation_sidecar_path,
    compute_record_hash,
    create_annotation_record,
    external_edit_requires_reindex,
    read_sidecar_records,
    reconcile_annotation_records,
    to_normalized_quad_points,
    to_viewport_rect,
    write_sidecar_records,
)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


def test_hl_pdf_03_normalized_quad_points_reproject_after_zoom():
    rect = {"left": 120, "top": 180, "width": 240, "height": 36}
    quad_points = to_normalized_quad_points(rect, page_width=600, page_height=800)

    assert all(0 <= point <= 1 for point in quad_points)
    at_100 = to_viewport_rect(quad_points, page_width=600, page_height=800, scale=1)
    at_175 = to_viewport_rect(quad_points, page_width=600, page_height=800, scale=1.75)

    assert at_100 == {"left": 120, "top": 180, "width": 240, "height": 36}
    assert at_175 == {"left": 210, "top": 315, "width": 420, "height": 63}


@pytest.mark.asyncio
async def test_hl_pdf_04_05_create_highlight_sidecar_uuid_hash_and_original_unchanged(session: AsyncSession, tmp_path: Path):
    pdf = tmp_path / "sources" / "papers" / "pdf" / "attention.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4\nattention fixture\n%%EOF")
    before_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    session.add(Source(id="src-attention", title="Attention Is All You Need"))
    await session.commit()

    record = create_annotation_record(
        source_id="src-attention",
        page=3,
        text="scaled dot-product attention",
        quad_points=[0.1, 0.2, 0.4, 0.2, 0.4, 0.24, 0.1, 0.24],
    )
    sidecar = write_sidecar_records(tmp_path, "src-attention", [record])
    await AnnotationIndexer(session, tmp_path).rebuild_from_sidecars("src-attention")

    assert sidecar == annotation_sidecar_path(tmp_path, "src-attention")
    assert len(record["sidecar_record_id"]) == 36
    assert record["rev"] == 1
    assert record["content_hash"] == compute_record_hash(record)
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == before_hash
    indexed = await session.get(Annotation, record["sidecar_record_id"])
    assert indexed is not None
    assert indexed.text == "scaled dot-product attention"


@pytest.mark.asyncio
async def test_hl_pdf_06_rebuild_from_sidecar_reproduces_records(session: AsyncSession, tmp_path: Path):
    records = [
        create_annotation_record(source_id="src-1", page=1, text="first", quad_points=[0.1, 0.1, 0.2, 0.1, 0.2, 0.2, 0.1, 0.2]),
        create_annotation_record(source_id="src-1", page=2, text="second", quad_points=[0.3, 0.3, 0.4, 0.3, 0.4, 0.4, 0.3, 0.4]),
    ]
    write_sidecar_records(tmp_path, "src-1", records)
    indexer = AnnotationIndexer(session, tmp_path)
    await indexer.rebuild_from_sidecars("src-1")
    await session.exec(delete(Annotation))
    await session.commit()

    rebuilt = await indexer.rebuild_from_sidecars("src-1")

    assert [row.sidecar_record_id for row in rebuilt] == [record["sidecar_record_id"] for record in records]
    assert [row.text for row in rebuilt] == ["first", "second"]


@pytest.mark.asyncio
async def test_hl_pdf_07_conflicts_resolve_by_rev_and_equal_rev_raises_review(session: AsyncSession, tmp_path: Path):
    base = create_annotation_record(source_id="src-1", page=1, text="old", quad_points=[0.1] * 8)
    older = {**base, "rev": 3, "text": "older"}
    older["content_hash"] = compute_record_hash(older)
    newer = {**base, "rev": 4, "text": "newer"}
    newer["content_hash"] = compute_record_hash(newer)

    resolved = await AnnotationIndexer(session, tmp_path).reconcile_records(older, newer)
    assert resolved["text"] == "newer"

    left = {**base, "rev": 5, "text": "left"}
    left["content_hash"] = compute_record_hash(left)
    right = {**base, "rev": 5, "text": "right"}
    right["content_hash"] = compute_record_hash(right)
    conflict = await AnnotationIndexer(session, tmp_path).reconcile_records(left, right)

    assert conflict["sidecar_record_id"] == base["sidecar_record_id"]
    review_items = (await session.exec(select(ReviewItem).where(ReviewItem.item_type == "annotation-conflict"))).all()
    assert len(review_items) == 1
    assert "mtime" not in review_items[0].summary.lower()
    assert reconcile_annotation_records(left, right).used_mtime is False


@pytest.mark.asyncio
async def test_hl_pdf_08_external_sidecar_edit_reindexes_sqlite(session: AsyncSession, tmp_path: Path):
    record = create_annotation_record(source_id="src-1", page=1, text="before", quad_points=[0.1] * 8)
    path = write_sidecar_records(tmp_path, "src-1", [record])
    indexer = AnnotationIndexer(session, tmp_path)
    await indexer.rebuild_from_sidecars("src-1")
    stored_sidecar_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    edited = {**record, "text": "after external edit", "rev": 2}
    edited["content_hash"] = compute_record_hash(edited)
    write_sidecar_records(tmp_path, "src-1", [edited])

    assert external_edit_requires_reindex(stored_sidecar_hash, path, app_wrote_last=False)
    await indexer.reindex_if_external_edit("src-1", stored_sidecar_hash, app_wrote_last=False)
    refreshed = await session.get(Annotation, record["sidecar_record_id"])
    assert refreshed.text == "after external edit"


@pytest.mark.asyncio
async def test_hl_pdf_09_claim_creation_suggests_by_default_and_auto_drafts_when_enabled(session: AsyncSession, tmp_path: Path):
    record = create_annotation_record(source_id="src-1", page=1, text="we propose a new simple network architecture", quad_points=[0.1] * 8)
    write_sidecar_records(tmp_path, "src-1", [record])
    indexer = AnnotationIndexer(session, tmp_path)
    await indexer.rebuild_from_sidecars("src-1")

    suggestion = await indexer.create_or_suggest_claim(record["sidecar_record_id"], auto_create=False)
    assert suggestion["created_claim"] is None
    assert suggestion["review_item"]["item_type"] == "annotation-claim-suggestion"
    assert (await session.exec(select(Claim))).all() == []

    created = await indexer.create_or_suggest_claim(record["sidecar_record_id"], auto_create=True)
    claim = await session.get(Claim, created["created_claim"]["id"])
    refreshed = await session.get(Annotation, record["sidecar_record_id"])
    assert claim.status == "draft"
    assert claim.id in refreshed.linked_claim_ids


@pytest.mark.asyncio
async def test_hl_refint_03_dangling_annotation_links_surface_review_item(session: AsyncSession, tmp_path: Path):
    note = Note(id="note-live", title="Live note")
    record = create_annotation_record(
        source_id="src-1",
        page=1,
        text="linked text",
        quad_points=[0.1] * 8,
        linked_claim_ids=["missing-claim"],
        linked_note_ids=[note.id],
    )
    session.add(note)
    await session.commit()
    write_sidecar_records(tmp_path, "src-1", [record])

    indexer = AnnotationIndexer(session, tmp_path)
    await indexer.rebuild_from_sidecars("src-1")
    findings = await indexer.scan_referential_integrity()

    assert findings[0]["missing_id"] == "missing-claim"
    review_items = (await session.exec(select(ReviewItem).where(ReviewItem.item_type == "annotation-broken-link"))).all()
    assert len(review_items) == 1
    assert review_items[0].origin_id == record["sidecar_record_id"]
