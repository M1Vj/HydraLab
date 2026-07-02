"""HydraLab-owned constrained wrapper around the system ``git`` CLI (HL-GIT-01..05).

Design constraints (spec Section 16 / 26.6 / DEC-6):
- Every invocation is an argv array; a shell is never used and untrusted strings
  are never interpolated into a shell.
- Read-only inspection subcommands map 1:1 to an allowlist. Off-list subcommands
  raise ``GitError`` and spawn nothing.
- Destructive operations (reset/checkout/clean/rebase/merge/push) require an
  explicit ``approved=True`` from the Git-UI approval flow and are NEVER reachable
  from the safe command console.
- All operations are scoped to the bound project workspace (``project_root``).
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Read-only inspection subcommands available to the Git panel AND the safe console.
READ_ONLY_SUBCOMMANDS: frozenset[str] = frozenset(
    {"status", "diff", "log", "branch", "show", "rev-parse", "ls-files"}
)

# Destructive subcommands — Git-UI approval only, never the console (HL-GIT-05).
DESTRUCTIVE_SUBCOMMANDS: frozenset[str] = frozenset(
    {"reset", "checkout", "clean", "rebase", "merge", "push"}
)


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int


class GitService:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()

    # -- low level -----------------------------------------------------------
    def _run(self, args: list[str]) -> GitResult:
        proc = subprocess.run(
            ["git", *args],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        return GitResult(
            ok=proc.returncode == 0,
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
        )

    def _run_read_only(self, subcommand: str, extra: Optional[list[str]] = None) -> GitResult:
        if subcommand not in READ_ONLY_SUBCOMMANDS:
            raise GitError(f"git subcommand not allowed: {subcommand}")
        return self._run([subcommand, *(extra or [])])

    def is_repo(self) -> bool:
        return (self.project_root / ".git").exists()

    # -- read-only inspection (HL-GIT-01) ------------------------------------
    def status(self) -> dict[str, object]:
        result = self._run_read_only("status", ["--porcelain=v1", "--untracked-files=all"])
        files: list[dict[str, str]] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            code = line[:2]
            path = line[3:]
            files.append({"code": code.strip() or code, "path": path})
        return {"branch": self.current_branch(), "changed_files": files, "clean": not files}

    def diff(self, path: Optional[str] = None) -> str:
        extra = ["--", path] if path else []
        return self._run_read_only("diff", extra).stdout

    def log(self, limit: int = 50) -> list[dict[str, str]]:
        fmt = "%H%x1f%an%x1f%at%x1f%s"
        result = self._run_read_only("log", [f"-n{limit}", f"--pretty=format:{fmt}"])
        commits: list[dict[str, str]] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("\x1f")
            if len(parts) == 4:
                commits.append({"hash": parts[0], "author": parts[1], "at": parts[2], "subject": parts[3]})
        return commits

    def current_branch(self) -> str:
        result = self._run_read_only("rev-parse", ["--abbrev-ref", "HEAD"])
        return result.stdout.strip() or "HEAD"

    # -- explicit safe writes ------------------------------------------------
    def commit(self, message: str, paths: Optional[list[str]] = None) -> dict[str, object]:
        """Record a commit. Only ever called from an explicit user click (HL-GIT-03)."""
        if not message.strip():
            raise GitError("commit message required")
        add_target = paths if paths else ["-A"]
        self._run(["add", *add_target])
        result = self._run(["commit", "-m", message])
        if not result.ok:
            raise GitError(result.stderr.strip() or "commit failed")
        head = self._run_read_only("rev-parse", ["HEAD"]).stdout.strip()
        return {"committed": True, "message": message, "branch": self.current_branch(), "commit": head}

    def checkpoint(self, label: str = "checkpoint") -> Optional[dict[str, object]]:
        """Auto-checkpoint commit before a risky action (HL-GIT-04)."""
        status = self.status()
        if status["clean"]:
            return None
        return self.commit(f"checkpoint: {label}", paths=None)

    def restore_previous_version(
        self, path: str, *, ref: str = "HEAD", auto_checkpoint: bool = False
    ) -> dict[str, object]:
        """Restore a file to a previous committed version (HL-GIT-01 / HL-GIT-04)."""
        # Resolve the target ref to a concrete commit BEFORE any checkpoint so an
        # auto-checkpoint (which advances HEAD) cannot capture the edit we are
        # about to discard as the "previous version".
        resolved = self._run(["rev-parse", ref]).stdout.strip() or ref
        checkpoint = None
        if auto_checkpoint:
            checkpoint = self.checkpoint(f"before restore {path}")
        result = self._run(["checkout", resolved, "--", path])
        if not result.ok:
            raise GitError(result.stderr.strip() or "restore failed")
        return {"restored": path, "ref": ref, "checkpoint": checkpoint}

    def destructive(self, subcommand: str, args: list[str], *, approved: bool) -> dict[str, object]:
        """Run a destructive op ONLY behind explicit Git-UI approval (HL-GIT-05)."""
        if subcommand not in DESTRUCTIVE_SUBCOMMANDS:
            raise GitError(f"not a recognized destructive git op: {subcommand}")
        if not approved:
            raise GitError("destructive git operation requires explicit UI approval")
        result = self._run([subcommand, *args])
        if not result.ok:
            raise GitError(result.stderr.strip() or f"{subcommand} failed")
        return {"ran": subcommand, "branch": self.current_branch()}


def suggest_grouped_commits(changed_files: list[dict[str, str]]) -> list[dict[str, object]]:
    """Suggest grouped commits with generated messages; NEVER commits (HL-GIT-03)."""
    groups: dict[str, list[str]] = {}
    for entry in changed_files:
        path = entry.get("path", "")
        top = path.split("/", 1)[0] if "/" in path else "root"
        groups.setdefault(top, []).append(path)

    prefix_by_area = {
        "knowledge": "docs",
        "writing": "docs",
        "drafts": "docs",
        "work": "chore",
        "sources": "chore",
    }
    suggestions: list[dict[str, object]] = []
    for area, files in sorted(groups.items()):
        prefix = prefix_by_area.get(area, "chore")
        label = area if area != "root" else "project"
        suggestions.append(
            {
                "message": f"{prefix}: update {label} ({len(files)} file{'s' if len(files) != 1 else ''})",
                "files": sorted(files),
            }
        )
    return suggestions
