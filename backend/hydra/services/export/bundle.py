"""Clean handoff exports: project ZIP + Markdown bundle (HL-EXPORT-02..04).

Every export excludes ``.hydralab/`` caches, temp files, raw internal logs, the
``.git`` directory and secrets by default. Chats, agent logs, browser snapshots
and annotations are per-category opt-ins. The DOCX slot is advertised as a
disabled ``setup required`` option until ``feature/01-12`` registers an exporter.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# Directories that are always excluded from any export.
_ALWAYS_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".venv"}
)

# ``.hydralab`` subfolders that are always excluded (caches/temp/raw logs/runtime).
_HYDRALAB_EXCLUDED = frozenset({"cache", "temp", "logs", "runtime", "indexes"})

# Secret-bearing files excluded by name/suffix.
_SECRET_FILENAMES = frozenset({".env", ".netrc", "credentials", "secrets"})
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")

# Raw-secret token prefixes to redact from any included text file.
SECRET_TOKEN_PREFIXES: tuple[str, ...] = (
    "sk-",
    "ai-",
    "ghp_",
    "github_pat_",
    "xoxb-",
    "xoxp-",
    "AKIA",
    "ASIA",
)

# Opt-in category → path-prefix membership test.
_OPT_IN_PREFIXES = {
    "chats": ("work/chats",),
    "agent_logs": ("work/agent-logs", ".hydralab/agent-logs"),
    "browser_snapshots": ("work/browser", "sources/browser"),
    "annotations": ("annotations",),
}


@dataclass
class ExportOptions:
    include_chats: bool = False
    include_agent_logs: bool = False
    include_browser_snapshots: bool = False
    include_annotations: bool = False

    def enabled_categories(self) -> set[str]:
        enabled = set()
        if self.include_chats:
            enabled.add("chats")
        if self.include_agent_logs:
            enabled.add("agent_logs")
        if self.include_browser_snapshots:
            enabled.add("browser_snapshots")
        if self.include_annotations:
            enabled.add("annotations")
        return enabled


def _is_secret_file(name: str) -> bool:
    lowered = name.lower()
    if lowered in _SECRET_FILENAMES or lowered.startswith(".env"):
        return True
    return any(lowered.endswith(suffix) for suffix in _SECRET_SUFFIXES)


def should_exclude(relative_path: str, options: Optional[ExportOptions] = None) -> bool:
    options = options or ExportOptions()
    parts = Path(relative_path).parts
    if not parts:
        return True
    if parts[0] in _ALWAYS_EXCLUDED_DIRS:
        return True
    if parts[0] == ".hydralab":
        if len(parts) > 1 and parts[1] in _HYDRALAB_EXCLUDED:
            return True
    if _is_secret_file(parts[-1]):
        return True
    posix = "/".join(parts)
    enabled = options.enabled_categories()
    for category, prefixes in _OPT_IN_PREFIXES.items():
        for prefix in prefixes:
            if posix == prefix or posix.startswith(prefix + "/") or f"/{prefix}/" in f"/{posix}":
                if category not in enabled:
                    return True
    return False


def scrub_secret_text(text: str) -> str:
    """Redact any inline raw-secret tokens from included text content."""
    out_lines: list[str] = []
    for line in text.splitlines():
        redacted = line
        for token in line.split():
            if token.startswith(SECRET_TOKEN_PREFIXES) and len(token) > 8:
                redacted = redacted.replace(token, "[REDACTED-SECRET]")
        out_lines.append(redacted)
    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(out_lines) + trailing


def _iter_project_files(project_root: Path) -> Iterable[Path]:
    for path in sorted(project_root.rglob("*")):
        if path.is_file():
            yield path


def build_project_zip(
    project_root: Path,
    *,
    selected_files: Optional[list[str]] = None,
    options: Optional[ExportOptions] = None,
) -> bytes:
    project_root = Path(project_root).resolve()
    options = options or ExportOptions()
    selected = set(selected_files) if selected_files is not None else None

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in _iter_project_files(project_root):
            relative = path.relative_to(project_root).as_posix()
            if should_exclude(relative, options):
                continue
            if selected is not None and relative not in selected:
                continue
            raw = path.read_bytes()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                archive.writestr(relative, raw)
                continue
            archive.writestr(relative, scrub_secret_text(text))
    buffer.seek(0)
    return buffer.getvalue()


def markdown_bundle(
    notes: list[dict[str, object]],
    citations_markdown: str = "",
    tasks_markdown: str = "",
) -> dict[str, str]:
    """Build a clean Markdown bundle (path → content), secrets scrubbed."""
    files: dict[str, str] = {}
    for note in notes:
        title = str(note.get("title") or f"note_{note.get('id')}")
        safe = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).rstrip() or f"note_{note.get('id')}"
        body = str(note.get("body") or "")
        files[f"knowledge/{safe}.md"] = scrub_secret_text(f"# {title}\n\n{body}\n")
    if citations_markdown:
        files["citations.md"] = scrub_secret_text(citations_markdown)
    if tasks_markdown:
        files["tasks.md"] = scrub_secret_text(tasks_markdown)
    return files


def export_options() -> dict[str, object]:
    """Advertise available export formats, including the disabled DOCX slot."""
    return {
        "citation_formats": ["bibtex", "csl", "ris"],
        "bundle_formats": [
            {"id": "markdown-bundle", "label": "Clean Markdown bundle", "available": True},
            {"id": "project-zip", "label": "Project ZIP (selected files)", "available": True},
            {
                "id": "docx",
                "label": "DOCX",
                "available": False,
                "state": "setup required",
                "message": "DOCX export requires the writing/DOCX exporter from feature/01-12.",
            },
        ],
        "opt_in_categories": ["chats", "agent_logs", "browser_snapshots", "annotations"],
        "excluded_by_default": [".hydralab/cache", ".hydralab/temp", ".hydralab/logs", ".git", "secrets/.env"],
    }
