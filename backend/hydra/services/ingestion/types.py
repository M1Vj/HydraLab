from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

TRUST_LEVEL_UNTRUSTED = "untrusted-external"
CONNECT_ONCE_STATE = "connect once to fetch models"


@dataclass(frozen=True)
class IngestionSource:
    source_id: str
    title: str
    path: Path
    project_root: Path
    declared_mime: str = ""


@dataclass(frozen=True)
class ArtifactPayload:
    kind: str
    engine: str
    relative_path: str
    content: bytes
    extraction_confidence: float
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractedImagePayload:
    relative_path: str
    content: bytes
    page: int
    bbox: dict[str, float]
    caption: str = ""


@dataclass(frozen=True)
class ArtifactSet:
    engine: str
    artifacts: list[ArtifactPayload]
    images: list[ExtractedImagePayload] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def text_artifacts(self) -> list[ArtifactPayload]:
        return [artifact for artifact in self.artifacts if artifact.kind in {"markdown", "text"}]

    def has_text(self) -> bool:
        return any(artifact.content.strip() for artifact in self.text_artifacts)


class EngineAdapter(Protocol):
    engine: str

    def convert(self, source: IngestionSource, output_dir: Path) -> ArtifactSet:
        ...


class IngestionError(Exception):
    status = "failed"


class QuarantineError(IngestionError):
    status = "quarantined"


class IncompleteExtractionError(IngestionError):
    status = "failed"


class MissingModelError(IngestionError):
    status = "failed"

    def __init__(self, message: str = CONNECT_ONCE_STATE):
        super().__init__(message)
