from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import (
    ConversionWarning,
    ExtractedImage,
    IngestionArtifact,
    IngestionJob,
    LexicalIndexEntry,
)
from hydra.services.ingestion.adapters import DoclingAdapter, LightExtractorAdapter, OptionalGrobidAdapter
from hydra.services.ingestion.safety import IngestionLimits, safe_artifact_path, validate_source_file
from hydra.services.ingestion.types import (
    CONNECT_ONCE_STATE,
    TRUST_LEVEL_UNTRUSTED,
    ArtifactPayload,
    ArtifactSet,
    EngineAdapter,
    IncompleteExtractionError,
    IngestionError,
    IngestionSource,
    MissingModelError,
    QuarantineError,
)

# Retrieval chunking: index the whole extracted document as overlapping windows
# rather than a single truncated prefix, so passages past the first page are
# still findable. Windows align to whitespace to avoid cutting mid-word, and the
# small overlap keeps a passage that straddles a boundary intact in one chunk.
_CHUNK_TARGET_CHARS = 1200
_CHUNK_OVERLAP_CHARS = 150


def chunk_document_text(
    text: str,
    *,
    target: int = _CHUNK_TARGET_CHARS,
    overlap: int = _CHUNK_OVERLAP_CHARS,
) -> list[tuple[int, str]]:
    """Split text into overlapping (char_offset, chunk_text) windows."""
    text = text.strip()
    if not text:
        return []
    chunks: list[tuple[int, str]] = []
    length = len(text)
    start = 0
    while start < length:
        end = min(start + target, length)
        if end < length:
            # Prefer a newline break, else a space, within the tail of the window.
            floor = start + overlap
            boundary = max(text.rfind("\n", floor, end), text.rfind(" ", floor, end))
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((start, chunk))
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks


class IngestionService:
    def __init__(
        self,
        *,
        primary_adapter: EngineAdapter | None = None,
        fallback_adapter: EngineAdapter | None = None,
        reference_adapter: OptionalGrobidAdapter | None = None,
        limits: IngestionLimits | None = None,
    ):
        self.limits = limits or IngestionLimits()
        self.primary_adapter = primary_adapter or DoclingAdapter(limits=self.limits)
        self.fallback_adapter = fallback_adapter or LightExtractorAdapter(limits=self.limits)
        self.reference_adapter = reference_adapter or OptionalGrobidAdapter(enabled=False)

    async def ingest(
        self,
        session: AsyncSession,
        *,
        source_id: str,
        title: str,
        source_path: Path,
        project_root: Path,
        declared_mime: str = "",
        job: IngestionJob | None = None,
    ) -> dict[str, object]:
        project_root = project_root.resolve()
        source_path = source_path.resolve()
        source = IngestionSource(
            source_id=source_id,
            title=title,
            path=source_path,
            project_root=project_root,
            declared_mime=declared_mime,
        )
        job = job or IngestionJob(source_id=source_id, source_path=str(source_path), status="queued")
        original_hash = _sha256_file(source_path) if source_path.exists() else ""
        job.original_content_hash = original_hash
        job.status = "running"
        job.progress = 5
        job.started_at = _now()
        session.add(job)
        await session.commit()
        await session.refresh(job)

        written_paths: list[Path] = []
        try:
            validate_source_file(source_path, declared_mime=declared_mime, limits=self.limits)
            artifact_set = self._convert(source)
            if _sha256_file(source_path) != original_hash:
                raise IngestionError("original source changed during ingestion")
            notes = list(artifact_set.notes)
            reference_result = self.reference_adapter.resolve(source)
            notes.extend(reference_result.notes)
            artifact_set = _append_reference_artifact(artifact_set, source, reference_result.engine, reference_result.metadata, reference_result.notes)
            artifact_rows = await self._persist_artifacts(session, source, job, artifact_set, written_paths)
            job.status = "done"
            job.progress = 100
            job.failure_reason = ""
            job.notes_json = json.dumps(notes, sort_keys=True)
            job.completed_at = _now()
            job.updated_at = _now()
            session.add(job)
            await session.commit()
            for row in artifact_rows:
                await session.refresh(row)
            await session.refresh(job)
            return {
                "state": job.status,
                "job_id": job.id,
                "engine": artifact_set.engine,
                "artifacts": [row.model_dump() for row in artifact_rows],
                "notes": notes,
            }
        except MissingModelError as exc:
            await self._rollback_artifacts(session, written_paths)
            await self._fail_job(session, job, "failed", str(exc))
            return {"state": CONNECT_ONCE_STATE, "job_id": job.id, "artifacts": [], "notes": [str(exc)]}
        except QuarantineError as exc:
            await self._rollback_artifacts(session, written_paths)
            await self._fail_job(session, job, "quarantined", str(exc))
            return {"state": "quarantined", "job_id": job.id, "artifacts": [], "reason": str(exc)}
        except IngestionError as exc:
            await self._rollback_artifacts(session, written_paths)
            await self._fail_job(session, job, "failed", str(exc))
            return {"state": "failed", "job_id": job.id, "artifacts": [], "reason": str(exc)}

    def _convert(self, source: IngestionSource) -> ArtifactSet:
        try:
            artifact_set = self.primary_adapter.convert(source, source.project_root / "sources" / "derived" / source.source_id)
            if not artifact_set.has_text():
                raise IncompleteExtractionError("primary adapter produced no text")
            return artifact_set
        except IncompleteExtractionError:
            return self.fallback_adapter.convert(source, source.project_root / "sources" / "derived" / source.source_id)

    async def _persist_artifacts(
        self,
        session: AsyncSession,
        source: IngestionSource,
        job: IngestionJob,
        artifact_set: ArtifactSet,
        written_paths: list[Path],
    ) -> list[IngestionArtifact]:
        rows: list[IngestionArtifact] = []
        image_parent: IngestionArtifact | None = None
        for artifact in artifact_set.artifacts:
            path = _write_artifact(source.project_root, artifact)
            written_paths.append(path)
            row = IngestionArtifact(
                source_id=source.source_id,
                job_id=job.id,
                engine=artifact.engine,
                kind=artifact.kind,
                path=str(path.relative_to(source.project_root)),
                content_hash=hashlib.sha256(artifact.content).hexdigest(),
                extraction_confidence=artifact.extraction_confidence,
                trust_level=TRUST_LEVEL_UNTRUSTED,
                warnings_json=json.dumps([*artifact_set.warnings, *artifact.warnings], sort_keys=True),
                metadata_json=json.dumps(artifact.metadata, sort_keys=True),
            )
            session.add(row)
            await session.flush()
            rows.append(row)
            if artifact.kind == "markdown" and artifact.content.strip():
                image_parent = row
                full_text = artifact.content.decode("utf-8", errors="ignore")
                for chunk_index, (char_offset, chunk_text) in enumerate(chunk_document_text(full_text)):
                    session.add(
                        LexicalIndexEntry(
                            source_id=source.source_id,
                            chunk_id=f"{row.id}:{chunk_index}",
                            locator=json.dumps(
                                {
                                    "artifact_id": row.id,
                                    "path": row.path,
                                    "chunk_index": chunk_index,
                                    "char_offset": char_offset,
                                }
                            ),
                            text=chunk_text,
                            trust_level=TRUST_LEVEL_UNTRUSTED,
                        )
                    )
            for warning in [*artifact_set.warnings, *artifact.warnings]:
                session.add(
                    ConversionWarning(
                        source_id=source.source_id,
                        job_id=job.id,
                        artifact_id=row.id,
                        code=_warning_code(warning),
                        message=warning,
                    )
                )

        for image in artifact_set.images:
            path = safe_artifact_path(source.project_root, image.relative_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image.content)
            written_paths.append(path)
            session.add(
                ExtractedImage(
                    source_id=source.source_id,
                    artifact_id=image_parent.id if image_parent else None,
                    path=str(path.relative_to(source.project_root)),
                    page=image.page,
                    bbox=json.dumps(image.bbox, sort_keys=True),
                    caption=image.caption,
                    trust_level=TRUST_LEVEL_UNTRUSTED,
                )
            )

        return rows

    async def _rollback_artifacts(self, session: AsyncSession, written_paths: list[Path]) -> None:
        await session.rollback()
        for path in reversed(written_paths):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass

    async def _fail_job(self, session: AsyncSession, job: IngestionJob, status: str, reason: str) -> None:
        job.status = status
        job.failure_reason = reason
        job.progress = 0
        job.completed_at = _now()
        job.updated_at = _now()
        session.add(job)
        await session.commit()


def _append_reference_artifact(
    artifact_set: ArtifactSet,
    source: IngestionSource,
    engine: str,
    metadata: dict[str, object],
    notes: list[str],
) -> ArtifactSet:
    base = f"sources/derived/{source.source_id}"
    artifact = ArtifactPayload(
        kind="reference_metadata",
        engine=engine,
        relative_path=f"{base}/reference-metadata.json",
        content=json.dumps({"metadata": metadata, "notes": notes}, sort_keys=True, indent=2).encode("utf-8"),
        extraction_confidence=0.75,
        warnings=notes,
        metadata=metadata,
    )
    return ArtifactSet(
        engine=artifact_set.engine,
        artifacts=[*artifact_set.artifacts, artifact],
        images=artifact_set.images,
        warnings=artifact_set.warnings,
        notes=[*artifact_set.notes, *notes],
    )


def _write_artifact(project_root: Path, artifact: ArtifactPayload) -> Path:
    path = safe_artifact_path(project_root, artifact.relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(artifact.content)
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _warning_code(warning: str) -> str:
    return warning.split(":", 1)[0].strip().lower().replace(" ", "-")[:80] or "warning"


def _now() -> datetime:
    return datetime.now(timezone.utc)
