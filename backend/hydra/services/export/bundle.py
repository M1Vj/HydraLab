"""Clean handoff exports: project ZIP + Markdown bundle (HL-EXPORT-02..04).

Every export excludes ``.hydralab/`` caches, temp files, raw internal logs, the
``.git`` directory and secrets by default. Chats, agent logs, browser snapshots
and annotations are per-category opt-ins. The DOCX slot is advertised as a
disabled ``setup required`` option until ``feature/01-12`` registers an exporter.
"""
from __future__ import annotations

import io
import re
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

# Raw-secret token prefixes retained for backward-compatible imports. Detection
# and scrubbing now use the regex engine below (``_SECRET_PATTERNS``); this tuple
# is no longer the matcher because whitespace-split prefix matching missed
# quoted, embedded (URL) and PEM-block secrets (HL privacy audit H1/H3).
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

# Canonical strong secret detector, shared by every clean-export/handoff path so
# the reproducibility bundle, project ZIP and Markdown bundle redact the same
# shapes the manuscript engine does. Uses ``re.search`` so a secret is caught
# regardless of quoting, surrounding URL/JSON punctuation or line topology. The
# multi-line PEM block pattern is first so scrubbing removes the whole key body,
# not just the BEGIN marker.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"\b(sk|rk)[-_][A-Za-z0-9_-]{8,}"),
    # NOTE: no bare ``ai-`` shape — it false-matches ordinary prose ("ai-generated",
    # "ai-assisted") and would corrupt/block manuscripts in an AI-research app.
    re.compile(r"\bxox[bpars]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{16,}"),
    re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{12,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
)


def text_contains_secret(text: str) -> bool:
    """True if ``text`` holds any provider/API/private-key secret shape."""
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)

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
    # Match an always-excluded dir at ANY depth, not just the first segment, so a
    # nested/submodule ``.git`` or vendored ``node_modules`` (e.g.
    # ``apps/web/.git/config`` carrying a credential remote URL) is excluded too
    # (HL privacy audit H2).
    if any(part in _ALWAYS_EXCLUDED_DIRS for part in parts):
        return True
    for index, part in enumerate(parts):
        if part == ".hydralab" and index + 1 < len(parts) and parts[index + 1] in _HYDRALAB_EXCLUDED:
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
    """Redact inline secrets (quoted, embedded, or PEM blocks) from text content."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED-SECRET]", text)
    return text


def _iter_project_files(project_root: Path) -> Iterable[Path]:
    # Skip symlinks: rglob does not descend symlinked dirs, but a FILE symlink is
    # is_file()-true and would otherwise copy an out-of-tree target's bytes (e.g.
    # ``notes/key -> ~/.ssh/id_rsa``) into the export (HL privacy audit M1).
    for path in sorted(project_root.rglob("*")):
        if path.is_symlink():
            continue
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
