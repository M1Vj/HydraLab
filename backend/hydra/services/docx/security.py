"""Untrusted-DOCX hardening (Section 34, DEC-11, HL-WRITE-22).

An imported ``.docx`` is an OOXML zip and may carry path-traversal entries,
macros (``vbaProject.bin``) or embedded active content. This module validates
the package, refuses any entry whose resolved path escapes the extraction root,
flags/skips macros and active content, and extracts only the safe parts into a
caller-owned temp directory. Imported text is data-not-instructions and cannot by
itself trigger any write/promotion — callers only ever read the extracted parts.
"""
from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath


ZIP_MAGIC = b"PK\x03\x04"

# Parts that carry macros or active content. Skipped and flagged, never honored.
ACTIVE_CONTENT_MARKERS = (
    "vbaproject.bin",
    "vbadata.xml",
    "activex",
    "/macros/",
    "ole",
)

MAX_ENTRIES = 4000
MAX_DECOMPRESSED = 80 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200.0


class DocxPackageError(ValueError):
    """Raised when the OOXML package is invalid or hostile (traversal, bad zip)."""


@dataclass
class SafeExtraction:
    root: Path
    members: list[str] = field(default_factory=list)
    flagged_active_content: list[str] = field(default_factory=list)


def _is_traversal(name: str) -> bool:
    if not name or "\x00" in name:
        return True
    normalized = name.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(name)
    if posix.is_absolute() or windows.is_absolute():
        return True
    if windows.drive or normalized.startswith("//"):
        return True
    if any(part == ".." for part in posix.parts):
        return True
    return False


def _is_active_content(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in ACTIVE_CONTENT_MARKERS)


def validate_ooxml_package(path: Path) -> None:
    """Validate magic bytes + zip structure; reject traversal and zip bombs."""
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise DocxPackageError(f"docx file does not exist: {path}")
    if path.read_bytes()[:4] != ZIP_MAGIC:
        raise DocxPackageError("file is not a valid OOXML package (missing ZIP magic bytes)")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                raise DocxPackageError("docx package entry count exceeded")
            names = {info.filename for info in infos}
            if "[Content_Types].xml" not in names:
                raise DocxPackageError("docx package missing [Content_Types].xml (not a valid OOXML document)")
            total = 0
            for info in infos:
                if _is_traversal(info.filename):
                    raise DocxPackageError(f"docx package entry escapes extraction root: {info.filename!r}")
                total += info.file_size
                if total > MAX_DECOMPRESSED:
                    raise DocxPackageError("docx package decompressed size limit exceeded")
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > MAX_COMPRESSION_RATIO:
                    raise DocxPackageError("docx package compression-ratio limit exceeded")
    except zipfile.BadZipFile as exc:
        raise DocxPackageError("invalid or corrupt docx zip archive") from exc


def extract_docx_safely(path: Path, dest: Path) -> SafeExtraction:
    """Extract only safe parts into ``dest``; reject traversal, flag/skip macros.

    Nothing is ever written outside ``dest``. Macro/active-content parts are
    flagged and skipped (never extracted, never executed).
    """
    validate_ooxml_package(path)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    extraction = SafeExtraction(root=root)

    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = info.filename
            if _is_traversal(name):
                raise DocxPackageError(f"docx package entry escapes extraction root: {name!r}")
            if _is_active_content(name):
                extraction.flagged_active_content.append(name)
                continue
            if name.endswith("/"):
                continue
            target = (root / name).resolve()
            # Defense in depth: confirm the resolved path is inside root.
            if os.path.commonpath([str(root), str(target)]) != str(root):
                raise DocxPackageError(f"docx package entry escapes extraction root: {name!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
            extraction.members.append(name)
    return extraction


def has_active_content(path: Path) -> list[str]:
    """Return the list of macro/active-content parts present in the package."""
    validate_ooxml_package(path)
    flagged: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if _is_active_content(name):
                flagged.append(name)
    return flagged
