"""DOCX import/view/export orchestration (Section 15, 10; HL-EXPORT-06..10).

Phase-1 scope is import + view + export only. Full native DOCX editing and
AI-assisted OpenXML structural edits (paragraph/run/style/comment/tracked-change
targeting) are Phase 2 (branch 02-08) and intentionally NOT exposed here.

Honest degradation (HL-EXPORT-08): when no converter is available every action
reports an ``unavailable`` state with the missing-capability reason and never a
fake success. Converter availability + version + setup error are persisted on a
``docx_artifact`` so the missing capability survives a restart (HL-EXPORT-09).

Export writes only under ``outputs/manuscripts/`` and never mutates the working
sources under ``writing/manuscripts/`` (HL-WRITE-20); a converter failure leaves
the source and any prior export unchanged (HL-EXPORT-10).
"""
from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .adapters import ConverterAdapter, ConverterAvailability, ImportedDocx, default_adapters
from .security import DocxPackageError

# Raw-secret shapes redacted from any exported manuscript (reuse of the hardened
# export secret-scrub posture — no secrets in output).
_SECRET_PATTERNS = [
    re.compile(r"\b(sk|ai|xoxb|xoxp)-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{12,}\b"),
]
_SECRET_REDACTION = "[redacted-secret]"


class DocxConverterError(RuntimeError):
    """Raised when an available converter fails mid-operation."""


def scrub_secrets(text: str) -> str:
    """Redact raw secret-shaped tokens so exports never leak credentials."""
    scrubbed = text
    for pattern in _SECRET_PATTERNS:
        scrubbed = pattern.sub(_SECRET_REDACTION, scrubbed)
    return scrubbed


@dataclass
class ExportResult:
    status: str  # "success" | "unavailable" | "failed"
    output_path: str | None = None
    converter: ConverterAvailability | None = None
    error_detail: str = ""


@dataclass
class ImportResult:
    status: str  # "success" | "unavailable" | "rejected"
    content: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    flagged_active_content: list[str] = field(default_factory=list)
    converter: ConverterAvailability | None = None
    error_detail: str = ""


class DocxService:
    def __init__(self, adapters: list[ConverterAdapter] | None = None) -> None:
        # ``None`` uses the default set; an empty list simulates "no converter".
        self.adapters = default_adapters() if adapters is None else adapters

    def detect(self) -> ConverterAvailability:
        """Return the first available adapter, else an unavailable summary."""
        errors: list[str] = []
        for adapter in self.adapters:
            availability = adapter.detect()
            if availability.available:
                return availability
            if availability.setup_error:
                errors.append(availability.setup_error)
        detail = "; ".join(errors) if errors else "No local DOCX converter is installed."
        return ConverterAvailability(adapter="none", available=False, setup_error=detail)

    def _active_adapter(self) -> tuple[ConverterAdapter | None, ConverterAvailability]:
        for adapter in self.adapters:
            availability = adapter.detect()
            if availability.available:
                return adapter, availability
        return None, self.detect()

    def import_docx(self, path: Path) -> ImportResult:
        """Import a DOCX: validate, harden, extract to temp, read, clean temp."""
        adapter, availability = self._active_adapter()
        if adapter is None:
            return ImportResult(status="unavailable", converter=availability, error_detail=availability.setup_error)

        temp_root = Path(tempfile.mkdtemp(prefix="hydralab-docx-"))
        try:
            imported: ImportedDocx = adapter.import_docx(Path(path), temp_root)
            return ImportResult(
                status="success",
                content=imported.content,
                metadata=imported.metadata,
                flagged_active_content=imported.flagged_active_content,
                converter=availability,
            )
        except DocxPackageError as exc:
            return ImportResult(status="rejected", converter=availability, error_detail=str(exc))
        except Exception as exc:
            return ImportResult(status="failed", converter=availability, error_detail=str(exc))
        finally:
            # Clean temp extraction files on success AND failure (HL-WRITE-22).
            shutil.rmtree(temp_root, ignore_errors=True)

    def export_manuscript(
        self,
        project_root: Path,
        manuscript: str,
        source_relpath: str,
        fmt: Any,
        *,
        bibliography: list[str] | None = None,
        output_name: str | None = None,
    ) -> ExportResult:
        """Export a manuscript source to DOCX under ``outputs/manuscripts/``.

        Writes to a temp file first and atomically moves it into place so a
        converter failure leaves any prior export unchanged (HL-EXPORT-10).
        """
        adapter, availability = self._active_adapter()
        if adapter is None:
            return ExportResult(status="unavailable", converter=availability, error_detail=availability.setup_error)

        project_root = Path(project_root)
        source_path = project_root / "writing" / "manuscripts" / manuscript / source_relpath
        if not source_path.exists():
            return ExportResult(status="failed", converter=availability, error_detail=f"source not found: {source_relpath}")

        text = scrub_secrets(source_path.read_text(encoding="utf-8"))
        if bibliography:
            text = text.rstrip() + "\n\n# References\n\n" + "\n".join(bibliography) + "\n"

        stem = output_name or (Path(source_relpath).stem + ".docx")
        if not stem.endswith(".docx"):
            stem += ".docx"
        out_dir = project_root / "outputs" / "manuscripts" / manuscript
        out_dir.mkdir(parents=True, exist_ok=True)
        final_path = out_dir / stem

        tmp_fd = tempfile.NamedTemporaryFile(prefix="hydralab-export-", suffix=".docx", delete=False)
        tmp_path = Path(tmp_fd.name)
        tmp_fd.close()
        try:
            adapter.export(text, tmp_path, fmt)
            shutil.move(str(tmp_path), str(final_path))
        except Exception as exc:  # converter failure: prior export untouched
            tmp_path.unlink(missing_ok=True)
            return ExportResult(status="failed", converter=availability, error_detail=str(exc))

        return ExportResult(status="success", output_path=str(final_path), converter=availability)


# --- LaTeX toolchain detection (HL-WRITE-19) --------------------------------

LATEX_BINARIES = ("tectonic", "latexmk", "xelatex", "pdflatex")


def detect_latex_toolchain() -> dict[str, Any]:
    """Detect a local TeX toolchain for the optional/staged compile surface.

    Returns availability + the discovered binary so the UI shows a setup/disabled
    state naming the missing toolchain rather than silently doing nothing.
    """
    for binary in LATEX_BINARIES:
        resolved = shutil.which(binary)
        if resolved:
            return {"available": True, "toolchain": binary, "path": resolved, "setup_error": ""}
    return {
        "available": False,
        "toolchain": "",
        "path": "",
        "setup_error": "No TeX toolchain (tectonic/latexmk/xelatex/pdflatex) detected. Install one to enable LaTeX compile/preview.",
    }
