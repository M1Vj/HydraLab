"""Pre-package privacy and redaction checks."""

from __future__ import annotations

import hashlib
from pathlib import Path

from hydra.services.export.bundle import text_contains_secret

from .models import ManuscriptDocument, RedactionItem, RedactionReport

_EXCLUDED_TOP_LEVEL = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}


class RedactionScanner:
    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)

    def scan(self, document: ManuscriptDocument) -> RedactionReport:
        paths = self._candidate_paths(document)
        items: list[RedactionItem] = []
        for relpath in paths:
            category, reason = self._classify_path(relpath)
            if category:
                items.append(_item(category, relpath, reason))
                continue
            absolute = self.project_root / relpath
            if absolute.is_file() and _looks_like_secret(absolute):
                items.append(_item("secrets", relpath, "file contains a raw secret-shaped token"))
        return RedactionReport(items=items)

    def _candidate_paths(self, document: ManuscriptDocument) -> list[str]:
        base = Path("writing") / "manuscripts" / document.manuscript_id
        paths = [str(base / relpath) for relpath in document.source_files]
        for relpath in document.include_paths:
            if _safe_relative(relpath):
                paths.append(str(Path(relpath)))
        return sorted(dict.fromkeys(paths))

    def _classify_path(self, relpath: str) -> tuple[str, str] | tuple[None, None]:
        path = Path(relpath)
        parts = path.parts
        if not parts:
            return None, None
        if any(part in _EXCLUDED_TOP_LEVEL for part in parts):
            return "excluded_folders", "path is in an excluded project folder"
        if parts[0] == ".hydralab" and len(parts) > 1 and parts[1] == "browser":
            return "hidden_browser_session_data", "hidden browser/session data is excluded from manuscript packages"
        if parts[0] == ".hydralab" and len(parts) > 1 and parts[1] == "logs":
            return "internal_logs", "internal logs are not packageable without acknowledgement"
        if len(parts) > 1 and parts[0] == "work" and parts[1] in {"reviews", "notes"}:
            return "private_notes", "private notes and reviews require removal or acknowledgement"
        if path.name.startswith(".env") or path.suffix in {".key", ".pem"}:
            return "secrets", "secret-bearing files are not packageable without acknowledgement"
        return None, None


def _item(category: str, relpath: str, reason: str) -> RedactionItem:
    digest = hashlib.sha256(f"{category}:{relpath}".encode("utf-8")).hexdigest()[:12]
    return RedactionItem(id=f"redact-{digest}", category=category, path=relpath, reason=reason)


def _safe_relative(value: str) -> bool:
    return bool(value) and ".." not in value and not value.startswith("/") and "\\" not in value and "\x00" not in value


def _looks_like_secret(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:200_000]
    except OSError:
        return False
    return text_contains_secret(text)
