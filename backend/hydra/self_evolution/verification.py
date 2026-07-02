"""Auto-verification adapter over the fixed allowlist runner (branch 03-05).

The fixer runs ONLY the HydraLab-owned verification allowlist (DEC-6); it never
executes arbitrary or model-authored shell. A change's ``test_plan`` names exact
commands that must each match this fixed allowlist before the change is
approvable, and they are spawned only through ``ConsoleService`` (the Phase-1/2
safe console) — this module adds no second free-form executor.

The runner is an injectable dependency so tests never actually shell out to
``pytest``/``bun`` (which would recurse/hang the outer suite); they pass a stub
that records the ``test_plan`` and returns a canned pass/fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from hydra.services.console import ConsoleService

# Fixed allowlist of verification command prefixes HydraLab owns (Section 26.6 /
# DEC-6). A test_plan entry is valid iff it equals a prefix or is that prefix
# followed by additional whitespace-separated arguments (e.g. a pytest path).
# This module MUST NOT widen this set.
ALLOWED_VERIFICATION_PREFIXES: tuple[str, ...] = (
    "bun run typecheck",
    "bun run lint",
    "bun run test",
    "bun run build",
    "uv run --project backend pytest",
    "uv run pytest",
)

# Maps an allowlisted command onto the ConsoleService verification NAME it runs
# through (ConsoleService only knows typecheck/lint/test/build by name).
_CONSOLE_NAME_BY_PREFIX: dict[str, str] = {
    "bun run typecheck": "typecheck",
    "bun run lint": "lint",
    "bun run test": "test",
    "bun run build": "build",
    "uv run --project backend pytest": "test",
    "uv run pytest": "test",
}


class TestPlanError(ValueError):
    """Raised when a test_plan is empty or names a non-allowlisted command."""

    __test__ = False  # not a pytest test class despite the "Test" prefix


def _normalize(command: str) -> str:
    return " ".join(str(command or "").strip().split())


def is_allowed_command(command: str) -> bool:
    normalized = _normalize(command)
    return any(
        normalized == prefix or normalized.startswith(prefix + " ")
        for prefix in ALLOWED_VERIFICATION_PREFIXES
    )


def validate_test_plan(test_plan: list[str]) -> list[str]:
    """Return the normalized test_plan or raise :class:`TestPlanError`.

    An empty plan is not approvable (HL-ASSIST-31); any entry outside the fixed
    verification allowlist is rejected rather than executed as free-form shell.
    """
    normalized = [_normalize(cmd) for cmd in (test_plan or []) if _normalize(cmd)]
    if not normalized:
        raise TestPlanError("a test plan is required before this change can be applied")
    for command in normalized:
        if not is_allowed_command(command):
            raise TestPlanError(
                f"test plan command is not in the verification allowlist: {command!r}"
            )
    return normalized


@dataclass
class VerificationOutcome:
    """Result of running a change's test_plan through the allowlist runner."""

    passed: bool
    commands: list[str] = field(default_factory=list)
    results: list[dict[str, object]] = field(default_factory=list)


class VerificationRunner(Protocol):
    def run(self, test_plan: list[str]) -> VerificationOutcome:  # pragma: no cover - protocol
        ...


class ConsoleVerificationRunner:
    """Default runner: validates then spawns each command via ConsoleService.

    Each allowlisted command maps to a ConsoleService verification name and runs
    with ``trigger="user"`` and first-use approval granted (the user explicitly
    approved this change). All commands must return 0 for the change to keep.
    This is the production path; tests inject a stub instead.
    """

    def __init__(self, project_root: Path, *, console: ConsoleService | None = None) -> None:
        self.project_root = Path(project_root)
        self.console = console or ConsoleService(self.project_root)

    def run(self, test_plan: list[str]) -> VerificationOutcome:
        commands = validate_test_plan(test_plan)
        results: list[dict[str, object]] = []
        passed = True
        for command in commands:
            name = _CONSOLE_NAME_BY_PREFIX[
                next(p for p in ALLOWED_VERIFICATION_PREFIXES if command == p or command.startswith(p + " "))
            ]
            result = self.console.run(name, trigger="user", approve=True, approved_commands=[name])
            ok = result.get("status") == "ran" and result.get("returncode") == 0
            passed = passed and ok
            results.append({"command": command, "console_name": name, "ok": ok, "status": result.get("status")})
        return VerificationOutcome(passed=passed, commands=commands, results=results)
