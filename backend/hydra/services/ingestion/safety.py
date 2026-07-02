from __future__ import annotations

import os
import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from .types import QuarantineError


@dataclass(frozen=True)
class IngestionLimits:
    max_file_size: int = 25 * 1024 * 1024
    max_pages: int = 200
    max_text_size: int = 5 * 1024 * 1024
    max_image_count: int = 100
    max_decompressed_size: int = 50 * 1024 * 1024
    max_archive_entries: int = 2000
    max_compression_ratio: float = 100.0
    max_archive_depth: int = 1
    timeout_seconds: int = 60


PDF_MAGIC = b"%PDF"
ZIP_MAGIC = b"PK\x03\x04"
TRUSTED_TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".html", ".htm", ".ris", ".bib", ".json"}
ZIP_EXTENSIONS = {".zip", ".docx", ".pptx"}


def validate_source_file(path: Path, declared_mime: str = "", limits: IngestionLimits | None = None) -> None:
    limits = limits or IngestionLimits()
    if not path.exists() or not path.is_file():
        raise QuarantineError(f"source file does not exist: {path}")
    size = path.stat().st_size
    if size > limits.max_file_size:
        raise QuarantineError(f"file exceeds max_file_size: {size} > {limits.max_file_size}")

    header = path.read_bytes()[:8]
    suffix = path.suffix.lower()
    if suffix == ".pdf" or declared_mime == "application/pdf":
        if not header.startswith(PDF_MAGIC):
            raise QuarantineError("file type mismatch: expected PDF magic bytes")
    elif suffix in ZIP_EXTENSIONS or declared_mime in {
        "application/zip",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }:
        if not header.startswith(ZIP_MAGIC):
            raise QuarantineError("file type mismatch: expected ZIP/OOXML magic bytes")
        validate_zip_archive(path, limits=limits)
    elif suffix in TRUSTED_TEXT_EXTENSIONS or declared_mime.startswith("text/"):
        path.read_text(encoding="utf-8", errors="ignore")
    else:
        raise QuarantineError(f"unsupported source type: {suffix or declared_mime or 'unknown'}")


def validate_zip_archive(path: Path, limits: IngestionLimits | None = None, depth: int = 0) -> None:
    limits = limits or IngestionLimits()
    if depth > limits.max_archive_depth:
        raise QuarantineError("archive nesting depth exceeded")
    total_size = 0
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > limits.max_archive_entries:
                raise QuarantineError("archive entry count exceeded")
            for info in infos:
                _validate_archive_name(info.filename)
                total_size += info.file_size
                if total_size > limits.max_decompressed_size:
                    raise QuarantineError("archive decompressed size limit exceeded")
                compressed = max(info.compress_size, 1)
                ratio = info.file_size / compressed
                if ratio > limits.max_compression_ratio:
                    raise QuarantineError("archive compression-ratio limit exceeded")
                if info.filename.lower().endswith(".zip"):
                    raise QuarantineError("nested archive rejected")
    except zipfile.BadZipFile as exc:
        raise QuarantineError("invalid zip archive") from exc


def safe_artifact_path(project_root: Path, relative_path: str) -> Path:
    normalized = posixpath.normpath(relative_path.replace("\\", "/"))
    _validate_archive_name(normalized)
    target = (project_root / normalized).resolve()
    root = project_root.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise QuarantineError("artifact path escapes project workspace") from exc
    return target


def _validate_archive_name(name: str) -> None:
    if not name or "\x00" in name:
        raise QuarantineError("archive entry has an invalid name")
    normalized = name.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(name)
    if posix.is_absolute() or windows.is_absolute():
        raise QuarantineError("archive entry uses an absolute path")
    if windows.drive or normalized.startswith("//"):
        raise QuarantineError("archive entry uses a drive or UNC prefix")
    if any(part in {"..", ""} for part in posix.parts):
        raise QuarantineError("archive entry contains path traversal")
    if os.path.islink(name):
        raise QuarantineError("archive symlink entries are not accepted")
