from __future__ import annotations

from pathlib import Path

from hydra.services.ingestion.safety import IngestionLimits
from hydra.services.ingestion.types import ArtifactPayload, ArtifactSet, IngestionSource


class LightExtractorAdapter:
    engine = "light"

    def __init__(self, limits: IngestionLimits | None = None):
        self.limits = limits or IngestionLimits()

    def convert(self, source: IngestionSource, output_dir: Path) -> ArtifactSet:
        text = self._extract_text(source.path)
        base = f"sources/derived/{source.source_id}"
        artifact = ArtifactPayload(
            kind="markdown",
            engine=self.engine,
            relative_path=f"{base}/document.light.md",
            content=text.encode("utf-8"),
            extraction_confidence=0.68 if text.strip() else 0.0,
            warnings=["docling fallback used"],
            metadata={"source_format": source.path.suffix.lower().lstrip(".") or "text"},
        )
        return ArtifactSet(engine=self.engine, artifacts=[artifact], warnings=["docling fallback used"])

    def _extract_text(self, path: Path) -> str:
        if path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader

                reader = PdfReader(str(path))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
                if text.strip():
                    return text[: self.limits.max_text_size]
            except Exception:
                pass
        return path.read_bytes().decode("utf-8", errors="ignore")[: self.limits.max_text_size]
