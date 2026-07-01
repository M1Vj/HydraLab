from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import Note, SchemaVersion
from hydra.settings.project_config import default_project_config, folder_role, save_project_config


SCHEMA_VERSION = "2026.01.02"
CORE_DIRS = ["sources", "knowledge", "work", "writing", "outputs"]
APP_DIRS = ["cache", "indexes", "temp", "logs"]
PAPER_FOLDERS = ["sources/papers/pdf", "sources/papers/metadata", "sources/papers/annotations"]


@dataclass(frozen=True)
class ProjectInitResult:
    root: Path
    project_id: str
    created: bool


@dataclass(frozen=True)
class GitInitDecision:
    action: str
    reason: str


def create_project(root: Path, name: str, git_enabled: bool = True) -> ProjectInitResult:
    root = Path(root)
    existed = root.exists() and any(root.iterdir()) if root.exists() else False
    root.mkdir(parents=True, exist_ok=True)

    for dirname in CORE_DIRS:
        (root / dirname).mkdir(exist_ok=True)
    hydralab = root / ".hydralab"
    hydralab.mkdir(exist_ok=True)
    for dirname in APP_DIRS:
        (hydralab / dirname).mkdir(exist_ok=True)

    project_id = _read_project_id(root / "project.yaml") or str(uuid.uuid4())
    _write_if_missing(root / "README.md", f"# {name}\n")
    _write_if_missing(root / "HYDRA.md", f"# {name} HydraLab Context\n\nProject-local assistant context. Do not store secrets here.\n")

    config = default_project_config(project_id, name)
    config["git"]["enabled"] = git_enabled
    save_project_config(root / "project.yaml", config)
    _init_project_db(hydralab / "hydralab.db")

    decision = evaluate_git_init(root, created_by_hydralab=not existed, git_enabled=git_enabled)
    if decision.action == "init":
        _run_git(root, ["init"])
        exclude = root / ".git" / "info" / "exclude"
        exclude.write_text(exclude.read_text() + "\n.hydralab/\n")
        _run_git(root, ["add", "README.md", "project.yaml", "HYDRA.md"])

    return ProjectInitResult(root=root, project_id=project_id, created=not existed)


def ensure_feature_folders(root: Path, feature: str) -> list[Path]:
    root = Path(root)
    if feature != "paper":
        raise ValueError(f"unsupported feature folder set: {feature}")
    created: list[Path] = []
    for relative in PAPER_FOLDERS:
        path = root / relative
        if not path.exists():
            created.append(path)
        path.mkdir(parents=True, exist_ok=True)
    return created


def evaluate_git_init(root: Path, created_by_hydralab: bool, git_enabled: bool) -> GitInitDecision:
    root = Path(root)
    if not git_enabled:
        return GitInitDecision("skip", "Git disabled by settings.")
    if (root / ".git").exists():
        return GitInitDecision("reuse", "Existing Git repository detected.")
    if not created_by_hydralab:
        return GitInitDecision("ask", "Existing non-Git folder requires user confirmation before git init.")
    return GitInitDecision("init", "New HydraLab-created project initializes Git by default.")


def is_git_tracked(root: Path, relative_path: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative_path],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


async def reindex_notes_from_canonical_files(root: Path, session: AsyncSession, project_id: str) -> list[str]:
    rebuilt: list[str] = []
    for path in _note_files(root):
        text = path.read_text()
        frontmatter, body = _split_frontmatter(text)
        note_id = frontmatter.get("note_id")
        if not note_id:
            continue
        title = frontmatter.get("title") or _first_heading(body) or path.stem
        note = await session.get(Note, note_id)
        if note is None:
            note = Note(id=note_id, workspace_id=project_id, project_id=project_id, title=title)
        note.relative_path = path.relative_to(root).as_posix()
        note.body = body
        note.title = title
        note.frontmatter = "{}"
        note.content_hash = hashlib.sha256(text.encode()).hexdigest()
        session.add(note)
        rebuilt.append(note_id)
    await session.commit()
    return rebuilt


def _init_project_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("create table if not exists schema_versions (component text primary key, version text not null, applied_at text not null)")
        conn.execute(
            "insert or replace into schema_versions (component, version, applied_at) values ('database', ?, datetime('now'))",
            (SCHEMA_VERSION,),
        )
        conn.commit()
    finally:
        conn.close()


def _read_project_id(path: Path) -> str | None:
    if not path.exists():
        return None
    match = re.search(r"^project_id:\s*(.+)$", path.read_text(), re.MULTILINE)
    return match.group(1).strip() if match else None


def _write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content)


def _run_git(root: Path, args: list[str]) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _note_files(root: Path) -> Iterable[Path]:
    for base in ("knowledge", "work", "writing"):
        directory = root / base
        if directory.exists():
            yield from directory.rglob("*.md")


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end].strip().splitlines()
    data: dict[str, str] = {}
    for line in raw:
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data, text[end + 4 :].lstrip()


def _first_heading(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None
