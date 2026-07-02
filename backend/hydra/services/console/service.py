"""Safe command console (HL-SAFE-02 / HL-SAFE-03, spec Section 26.6 / DEC-6).

"No code execution" means "no arbitrary/user-authored code execution". The ONLY
executable commands are:
  1. read-only Git inspection (status/diff/log/branch), and
  2. a FIXED HydraLab-owned verification allowlist (typecheck/lint/test/build).

Everything else is rejected with ``command not allowed`` and spawns nothing.
Verification commands come from HydraLab-owned trusted config (name → argv array,
never a project ``package.json`` script body), are spawned with an argv array and
no shell interpolation, require explicit per-project first-use approval, are
blocked when the trigger is the assistant or untrusted content, are disabled in
offline/locked-down posture, and run only inside the project workspace.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Iterable, Optional

from hydra.services.git.service import GitService

COMMAND_NOT_ALLOWED = "command not allowed"

# Read-only git inspection commands exposed through the console.
GIT_CONSOLE_COMMANDS: dict[str, tuple[str, list[str]]] = {
    "git status": ("status", []),
    "git diff": ("diff", []),
    "git log": ("log", []),
    "git branch": ("branch", []),
}

VERIFICATION_COMMANDS: frozenset[str] = frozenset({"typecheck", "lint", "test", "build"})

# HydraLab-owned trusted config: verification name → argv array. These reference
# HydraLab's chosen runner by name; they are NOT copied from project script bodies.
DEFAULT_VERIFICATION_CONFIG: dict[str, list[str]] = {
    "typecheck": ["bun", "run", "typecheck"],
    "lint": ["bun", "run", "lint"],
    "test": ["bun", "run", "test"],
    "build": ["bun", "run", "build"],
}

SpawnFn = Callable[[list[str], Path], "subprocess.CompletedProcess[str]"]


def _default_spawn(argv: list[str], cwd: Path) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False, shell=False)


class ConsoleService:
    def __init__(
        self,
        project_root: Path,
        *,
        verification_config: Optional[dict[str, list[str]]] = None,
        offline: bool = False,
        git_service: Optional[GitService] = None,
        spawn: Optional[SpawnFn] = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.verification_config = verification_config or DEFAULT_VERIFICATION_CONFIG
        self.offline = offline
        self.git_service = git_service or GitService(self.project_root)
        self._spawn = spawn or _default_spawn

    def run(
        self,
        command: str,
        *,
        trigger: str = "user",
        approve: bool = False,
        approved_commands: Iterable[str] = (),
    ) -> dict[str, object]:
        normalized = " ".join(command.strip().split())
        approved = set(approved_commands)

        # 1. Read-only git inspection — always available, including offline.
        if normalized in GIT_CONSOLE_COMMANDS:
            subcommand, extra = GIT_CONSOLE_COMMANDS[normalized]
            result = self.git_service._run_read_only(subcommand, extra)
            return {
                "status": "ran",
                "command": normalized,
                "kind": "git",
                "output": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "spawned": True,
            }

        # 2. Verification allowlist (trusted config).
        if normalized in VERIFICATION_COMMANDS:
            # HL-SAFE-03: only an explicit researcher action may trigger verification.
            if trigger != "user":
                return {
                    "status": "blocked",
                    "command": normalized,
                    "message": "verification runs only from an explicit researcher action in the console",
                    "spawned": False,
                }
            # HL-SAFE-03: disabled in offline/locked-down posture.
            if self.offline:
                return {
                    "status": "disabled",
                    "command": normalized,
                    "message": "verification commands are disabled in offline/locked-down posture",
                    "spawned": False,
                }
            # HL-SAFE-03: per-project first-use approval.
            first_use = normalized not in approved
            if first_use and not approve:
                return {
                    "status": "approval_required",
                    "command": normalized,
                    "message": f"first-use approval required for verification command '{normalized}'",
                    "spawned": False,
                }
            argv = self.verification_config.get(normalized)
            if not argv:
                return {"status": "rejected", "command": normalized, "message": COMMAND_NOT_ALLOWED, "spawned": False}
            proc = self._spawn(list(argv), self.project_root)
            payload: dict[str, object] = {
                "status": "ran",
                "command": normalized,
                "kind": "verification",
                "output": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
                "spawned": True,
            }
            if first_use and approve:
                payload["approved_now"] = normalized
            return payload

        # 3. Everything else is rejected and spawns nothing (HL-SAFE-02).
        return {"status": "rejected", "command": normalized, "message": COMMAND_NOT_ALLOWED, "spawned": False}
