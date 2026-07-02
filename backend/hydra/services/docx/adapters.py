"""DOCX converter adapters (HL-EXPORT-06/07/08/09, HL-LIC-04).

One HydraLab-owned adapter interface (``detect`` / ``import_docx`` / ``export``)
backed by:

- :class:`PythonDocxAdapter` — the BUNDLED default (python-docx, SPDX ``MIT``),
  fully permissive, used for both read and write so the shipped path carries no
  strong-copyleft dependency (HL-LIC-04).
- :class:`PandocAdapter` — OPTIONAL, non-bundled. Pandoc is GPL, so it is only
  ever invoked as a separate external subprocess against a user-installed binary
  (mere invocation, not linking); absent by default with graceful degradation.
- :class:`LibreOfficeAdapter` — OPTIONAL, non-bundled ``soffice`` subprocess.

``detect()`` reports availability so the UI can show an honest setup/disabled
state instead of a fake success when no converter is present.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .security import extract_docx_safely, has_active_content


@dataclass
class ConverterAvailability:
    adapter: str
    version: str = ""
    available: bool = False
    setup_error: str = ""

    @property
    def status(self) -> str:
        return "available" if self.available else "unavailable"


@dataclass
class ImportedDocx:
    content: str
    metadata: dict[str, str]
    flagged_active_content: list[str] = field(default_factory=list)


class ConverterAdapter(Protocol):
    name: str

    def detect(self) -> ConverterAvailability: ...

    def import_docx(self, path: Path, extract_root: Path) -> ImportedDocx: ...

    def export(self, text: str, out_path: Path, fmt) -> None: ...


class PythonDocxAdapter:
    """Bundled MIT adapter using python-docx for read + write."""

    name = "python-docx"

    def detect(self) -> ConverterAvailability:
        try:
            import docx  # noqa: F401
            from importlib.metadata import version

            try:
                ver = version("python-docx")
            except Exception:
                ver = "unknown"
            return ConverterAvailability(adapter=self.name, version=ver, available=True)
        except Exception as exc:  # pragma: no cover - only when python-docx missing
            return ConverterAvailability(
                adapter=self.name,
                available=False,
                setup_error=f"python-docx is not installed: {exc}",
            )

    def import_docx(self, path: Path, extract_root: Path) -> ImportedDocx:
        # Safe extraction first (validates package, refuses traversal, flags macros).
        extraction = extract_docx_safely(path, extract_root)
        import docx

        document = docx.Document(str(path))
        paragraphs = [p.text for p in document.paragraphs]
        content = "\n".join(paragraphs).strip()
        core = document.core_properties
        metadata: dict[str, str] = {}
        if core.title:
            metadata["title"] = core.title
        if core.author:
            metadata["author"] = core.author
        if core.created:
            metadata["created"] = core.created.isoformat()
        if core.modified:
            metadata["modified"] = core.modified.isoformat()
        return ImportedDocx(
            content=content,
            metadata=metadata,
            flagged_active_content=extraction.flagged_active_content,
        )

    def export(self, text: str, out_path: Path, fmt) -> None:
        import docx
        from docx.enum.section import WD_ORIENT
        from docx.shared import Inches, Pt

        document = docx.Document()

        # Base font.
        normal = document.styles["Normal"]
        normal.font.name = fmt.font_family
        try:
            size = float(str(fmt.font_size).lower().replace("pt", "").replace("px", ""))
            normal.font.size = Pt(size)
        except (TypeError, ValueError):
            pass

        # Page geometry.
        section = document.sections[0]
        try:
            inches = float(str(fmt.margins).lower().replace("in", "").replace("cm", ""))
            for attr in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
                setattr(section, attr, Inches(inches))
        except (TypeError, ValueError):
            pass
        if fmt.orientation == "landscape":
            section.orientation = WD_ORIENT.LANDSCAPE
            section.page_width, section.page_height = section.page_height, section.page_width

        # Line spacing on the Normal paragraph format.
        normal.paragraph_format.line_spacing = float(fmt.line_spacing)

        heading_counter = 0
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line:
                continue
            if line.startswith("## "):
                heading_counter += 1
                prefix = f"{heading_counter} " if fmt.heading_numbering else ""
                document.add_heading(f"{prefix}{line[3:].strip()}", level=2)
            elif line.startswith("# "):
                heading_counter += 1
                prefix = f"{heading_counter} " if fmt.heading_numbering else ""
                document.add_heading(f"{prefix}{line[2:].strip()}", level=1)
            else:
                paragraph = document.add_paragraph(line)
                paragraph.paragraph_format.line_spacing = float(fmt.line_spacing)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        document.save(str(out_path))


class _SubprocessAdapter:
    """Shared detection for optional external, non-bundled converter binaries."""

    binary = ""
    name = ""

    def detect(self) -> ConverterAvailability:
        resolved = shutil.which(self.binary)
        if not resolved:
            return ConverterAvailability(
                adapter=self.name,
                available=False,
                setup_error=f"{self.binary} is not installed; install it to enable this converter.",
            )
        version = ""
        try:
            proc = subprocess.run(
                [resolved, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            version = (proc.stdout or proc.stderr or "").splitlines()[0].strip()[:120]
        except Exception:
            version = "unknown"
        return ConverterAvailability(adapter=self.name, version=version, available=True)


class PandocAdapter(_SubprocessAdapter):
    """Optional, non-bundled Pandoc (GPL) — invoked as an external subprocess."""

    binary = "pandoc"
    name = "pandoc"

    def import_docx(self, path: Path, extract_root: Path) -> ImportedDocx:
        flagged = has_active_content(path)
        resolved = shutil.which(self.binary)
        proc = subprocess.run(
            [resolved, "-f", "docx", "-t", "gfm", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"pandoc import failed: {proc.stderr.strip()}")
        return ImportedDocx(content=proc.stdout.strip(), metadata={}, flagged_active_content=flagged)

    def export(self, text: str, out_path: Path, fmt) -> None:
        resolved = shutil.which(self.binary)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [resolved, "-f", "gfm", "-t", "docx", "-o", str(out_path)],
            input=text,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"pandoc export failed: {proc.stderr.strip()}")


class LibreOfficeAdapter(_SubprocessAdapter):
    """Optional, non-bundled LibreOffice headless (``soffice``) subprocess."""

    binary = "soffice"
    name = "libreoffice"

    def import_docx(self, path: Path, extract_root: Path) -> ImportedDocx:
        # Reuse the bundled reader for content; soffice is used for export only.
        return PythonDocxAdapter().import_docx(path, extract_root)

    def export(self, text: str, out_path: Path, fmt) -> None:  # pragma: no cover - env dependent
        raise RuntimeError("LibreOffice export is handled via the bundled adapter in Phase 1")


# Ordered preference: bundled permissive first, optional external after.
def default_adapters() -> list[ConverterAdapter]:
    return [PythonDocxAdapter(), PandocAdapter(), LibreOfficeAdapter()]
