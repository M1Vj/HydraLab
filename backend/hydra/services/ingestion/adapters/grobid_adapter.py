from __future__ import annotations

from dataclasses import dataclass

from hydra.services.ingestion.types import IngestionSource


@dataclass(frozen=True)
class ReferenceMetadataResult:
    engine: str
    metadata: dict[str, object]
    notes: list[str]


class OptionalGrobidAdapter:
    engine = "grobid"

    def __init__(self, enabled: bool = False, reachable: bool = False):
        self.enabled = enabled
        self.reachable = reachable

    def resolve(self, source: IngestionSource) -> ReferenceMetadataResult:
        if not self.enabled or not self.reachable:
            return ReferenceMetadataResult(
                engine="scholarly-api",
                metadata={"title": source.title, "source_id": source.source_id, "references": []},
                notes=["grobid: unavailable"],
            )
        return ReferenceMetadataResult(
            engine=self.engine,
            metadata={"title": source.title, "source_id": source.source_id, "references": []},
            notes=[],
        )
