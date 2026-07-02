from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import (
    ConversionWarning,
    ExtractedImage,
    IngestionArtifact,
    IngestionJob,
    LexicalIndexEntry,
    Source,
)
from hydra.services.ingestion.adapters import DoclingAdapter
from hydra.services.ingestion.queue import IngestionQueue
from hydra.services.ingestion.service import IngestionService
from hydra.services.ingestion.safety import IngestionLimits, validate_zip_archive
from hydra.services.ingestion.types import ArtifactPayload, ArtifactSet, IncompleteExtractionError, IngestionSource

FIXTURES = Path(__file__).parent / "fixtures" / "ingestion"


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


@pytest.mark.asyncio
async def test_hl_ingest_02_docling_writes_markdown_json_and_preserves_original(session: AsyncSession, tmp_path: Path):
    original = tmp_path / "sources" / "originals" / "attention.pdf"
    original.parent.mkdir(parents=True)
    original.write_bytes((FIXTURES / "sample-paper.pdf").read_bytes())
    before = original.read_bytes()
    session.add(Source(id="src-attention", title="Attention Is All You Need"))
    await session.commit()

    result = await IngestionService().ingest(
        session,
        source_id="src-attention",
        title="Attention Is All You Need",
        source_path=original,
        project_root=tmp_path,
        declared_mime="application/pdf",
    )

    assert result["state"] == "done"
    assert original.read_bytes() == before
    artifacts = (await session.exec(select(IngestionArtifact))).all()
    assert {artifact.kind for artifact in artifacts} >= {"markdown", "structured_json", "reference_metadata"}
    assert {artifact.engine for artifact in artifacts if artifact.kind in {"markdown", "structured_json"}} == {"docling"}
    assert all(artifact.trust_level == "untrusted-external" for artifact in artifacts)
    assert all((tmp_path / artifact.path).exists() for artifact in artifacts)
    images = (await session.exec(select(ExtractedImage))).all()
    assert len(images) == 1
    assert images[0].page == 1
    assert "width" in images[0].bbox


@pytest.mark.asyncio
async def test_hl_ingest_03_incomplete_docling_falls_back_to_light_extractor(session: AsyncSession, tmp_path: Path):
    class EmptyDocling:
        engine = "docling"

        def convert(self, source: IngestionSource, output_dir: Path) -> ArtifactSet:
            raise IncompleteExtractionError("docling produced zero text pages")

    original = tmp_path / "sources" / "originals" / "fallback.md"
    original.parent.mkdir(parents=True)
    original.write_text("Fallback extractor should keep this text.")
    session.add(Source(id="src-fallback", title="Fallback"))
    await session.commit()

    result = await IngestionService(primary_adapter=EmptyDocling()).ingest(
        session,
        source_id="src-fallback",
        title="Fallback",
        source_path=original,
        project_root=tmp_path,
        declared_mime="text/markdown",
    )

    assert result["state"] == "done"
    artifacts = (await session.exec(select(IngestionArtifact).where(IngestionArtifact.kind == "markdown"))).all()
    assert artifacts[0].engine == "light"


@pytest.mark.asyncio
async def test_hl_ingest_04_grobid_disabled_records_unavailable_note(session: AsyncSession, tmp_path: Path):
    original = tmp_path / "sources" / "originals" / "paper.md"
    original.parent.mkdir(parents=True)
    original.write_text("A paper with DOI 10.48550/arXiv.1706.03762.")
    session.add(Source(id="src-grobid", title="GROBID Optional"))
    await session.commit()

    result = await IngestionService().ingest(
        session,
        source_id="src-grobid",
        title="GROBID Optional",
        source_path=original,
        project_root=tmp_path,
        declared_mime="text/markdown",
    )

    assert result["state"] == "done"
    assert "grobid: unavailable" in result["notes"]
    warnings = (await session.exec(select(ConversionWarning))).all()
    assert any(warning.message == "grobid: unavailable" for warning in warnings)


@pytest.mark.asyncio
async def test_hl_ingest_01_queue_pause_resume_priority_persists_across_restart(session: AsyncSession, tmp_path: Path):
    queue = IngestionQueue(session, max_parallel_jobs=2)
    low = await queue.enqueue(source_id="src-low", source_path=tmp_path / "low.pdf", priority=0)
    high = await queue.enqueue(source_id="src-high", source_path=tmp_path / "high.pdf", priority=0)
    await queue.pause(low.id)
    await queue.set_priority(high.id, 10)

    restarted_queue = IngestionQueue(session, max_parallel_jobs=2)
    pending = await restarted_queue.resume_after_restart()

    assert [job.id for job in pending] == [high.id]
    assert (await session.get(IngestionJob, low.id)).status == "paused"


@pytest.mark.asyncio
async def test_hl_trust_01_artifacts_and_chunks_are_untrusted_external(session: AsyncSession, tmp_path: Path):
    original = tmp_path / "sources" / "originals" / "injection.md"
    original.parent.mkdir(parents=True)
    original.write_bytes((FIXTURES / "instruction-injection.md").read_bytes())
    session.add(Source(id="src-injection", title="Injection Fixture"))
    await session.commit()

    result = await IngestionService().ingest(
        session,
        source_id="src-injection",
        title="Injection Fixture",
        source_path=original,
        project_root=tmp_path,
        declared_mime="text/markdown",
    )

    assert result["state"] == "done"
    artifacts = (await session.exec(select(IngestionArtifact))).all()
    chunks = (await session.exec(select(LexicalIndexEntry))).all()
    assert artifacts
    assert chunks
    assert {artifact.trust_level for artifact in artifacts} == {"untrusted-external"}
    assert {chunk.trust_level for chunk in chunks} == {"untrusted-external"}
    assert (await session.exec(select(Source))).all()[0].id == "src-injection"


@pytest.mark.asyncio
async def test_hl_trust_02_rejects_type_mismatch_and_path_traversal(session: AsyncSession, tmp_path: Path):
    fake_pdf = tmp_path / "sources" / "originals" / "fake.pdf"
    fake_pdf.parent.mkdir(parents=True)
    fake_pdf.write_text("not a pdf")
    session.add(Source(id="src-bad", title="Bad PDF"))
    await session.commit()

    result = await IngestionService().ingest(
        session,
        source_id="src-bad",
        title="Bad PDF",
        source_path=fake_pdf,
        project_root=tmp_path,
        declared_mime="application/pdf",
    )

    assert result["state"] == "quarantined"
    assert "magic bytes" in result["reason"]
    assert not (tmp_path / "sources" / "derived" / "src-bad").exists()

    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../../escape.txt", "escape")
    with pytest.raises(Exception, match="path traversal"):
        validate_zip_archive(traversal)


@pytest.mark.asyncio
async def test_hl_trust_02_rejects_zip_bomb_ratio(session: AsyncSession, tmp_path: Path):
    bomb = tmp_path / "bomb.docx"
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "A" * 200_000)

    limits = IngestionLimits(max_decompressed_size=500_000, max_compression_ratio=5)
    with pytest.raises(Exception, match="compression-ratio"):
        validate_zip_archive(bomb, limits=limits)


@pytest.mark.asyncio
async def test_hl_ingest_08_offline_without_models_returns_connect_once_state(session: AsyncSession, tmp_path: Path):
    original = tmp_path / "sources" / "originals" / "paper.pdf"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"%PDF-1.4\nNeeds models\n%%EOF")
    session.add(Source(id="src-offline", title="Offline Models"))
    await session.commit()

    result = await IngestionService(primary_adapter=DoclingAdapter(models_present=False, offline=True)).ingest(
        session,
        source_id="src-offline",
        title="Offline Models",
        source_path=original,
        project_root=tmp_path,
        declared_mime="application/pdf",
    )

    assert result["state"] == "connect once to fetch models"
    assert (await session.exec(select(IngestionArtifact))).all() == []


@pytest.mark.asyncio
async def test_failed_ingestion_original_mutation_rolls_back_artifact_rows_and_files(session: AsyncSession, tmp_path: Path):
    class MutatingAdapter:
        engine = "mutating"

        def convert(self, source: IngestionSource, output_dir: Path) -> ArtifactSet:
            source.path.write_text("changed during conversion")
            return ArtifactSet(
                engine=self.engine,
                artifacts=[
                    ArtifactPayload(
                        kind="markdown",
                        engine=self.engine,
                        relative_path=f"sources/derived/{source.source_id}/document.md",
                        content=b"should not persist",
                        extraction_confidence=0.5,
                    )
                ],
            )

    original = tmp_path / "sources" / "originals" / "paper.md"
    original.parent.mkdir(parents=True)
    original.write_text("stable before conversion")
    session.add(Source(id="src-mutated", title="Mutated"))
    await session.commit()

    result = await IngestionService(primary_adapter=MutatingAdapter()).ingest(
        session,
        source_id="src-mutated",
        title="Mutated",
        source_path=original,
        project_root=tmp_path,
        declared_mime="text/markdown",
    )

    assert result["state"] == "failed"
    assert "original source changed" in result["reason"]
    assert (await session.exec(select(IngestionArtifact))).all() == []
    assert list((tmp_path / "sources" / "derived").glob("**/*")) == []
    job = (await session.exec(select(IngestionJob))).one()
    assert job.status == "failed"
