from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

GLOBAL_CONTEXT_FILES = ("SOUL.md", "USER.md", "MEMORY.md")
PROJECT_CONTEXT_FILE = "HYDRA.md"


@dataclass
class ContextFile:
    name: str
    path: str
    content: str
    scope: str  # global / project
    recovery: str  # logs-only / git-checkpoint
    exists: bool = True
    visible: bool = True  # visible project context, not a hidden system prompt


@dataclass
class ContextBundle:
    profile_id: str
    global_files: list[ContextFile] = field(default_factory=list)
    project_file: ContextFile | None = None


def load_global_context(profile_root: Path, profile_id: str = "default") -> list[ContextFile]:
    """Load the three global context files for a profile.

    The signature accepts an explicit ``profile_root``/``profile_id`` so multi-profile
    support is addable without a redesign (HL-ASSIST-12). Phase 1 uses one profile.
    """
    profile_root = Path(profile_root)
    files: list[ContextFile] = []
    for name in GLOBAL_CONTEXT_FILES:
        path = profile_root / name
        exists = path.exists()
        content = path.read_text(encoding="utf-8") if exists else ""
        files.append(
            ContextFile(name=name, path=str(path), content=content, scope="global", recovery="logs-only", exists=exists)
        )
    return files


def load_project_context(project_root: Path) -> ContextFile:
    """Load project-local HYDRA.md as visible context (not a hidden system prompt)."""
    project_root = Path(project_root)
    path = project_root / PROJECT_CONTEXT_FILE
    exists = path.exists()
    content = path.read_text(encoding="utf-8") if exists else ""
    return ContextFile(
        name=PROJECT_CONTEXT_FILE,
        path=str(path),
        content=content,
        scope="project",
        recovery="git-checkpoint",
        exists=exists,
        visible=True,
    )


def load_context_bundle(project_root: Path, profile_root: Path, profile_id: str = "default") -> ContextBundle:
    return ContextBundle(
        profile_id=profile_id,
        global_files=load_global_context(profile_root, profile_id),
        project_file=load_project_context(project_root),
    )


def ensure_hydra_md(project_root: Path) -> Path:
    """Create HYDRA.md if missing and ensure it is Git-tracked by default."""
    project_root = Path(project_root)
    path = project_root / PROJECT_CONTEXT_FILE
    if not path.exists():
        path.write_text("# HYDRA.md\n\nProject context for the assistant. Readable and editable.\n", encoding="utf-8")
    if (project_root / ".git").exists():
        subprocess.run(
            ["git", "add", PROJECT_CONTEXT_FILE],
            cwd=project_root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return path
