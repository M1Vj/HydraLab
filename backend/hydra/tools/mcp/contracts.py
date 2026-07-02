"""Thin local agent-runtime contracts for the MCP surface.

# RECONCILE-WITH-02-01: replace with hydra.agents.* contract at merge.
#
# Branch feature/02-01-agent-runtime-skills owns the canonical agent-runtime
# permission contract, the delimited untrusted region, and the run-trace store.
# 02-01 is built in parallel and is NOT yet merged into this base, so the pieces
# below are a MINIMAL, self-contained shim that keeps 02-02 buildable and
# testable. At integration, swap:
#   - resolve_tool_permission()  -> hydra.agents permission resolver
#   - the McpTracePort protocol   -> hydra.agents run-trace store
# The untrusted-region delimiter re-uses the ALREADY-SHIPPED Phase-1 contract in
# hydra.services.assistant.untrusted (not a shim); it is wrapped here only to
# tag MCP provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from hydra.services.assistant.untrusted import assemble_untrusted_region
from hydra.services.browser.actions import browser_copilot_tool_descriptors

# HL-TRUST-04 / DEC-6: the Section 26.6 verification allowlist is the ONLY
# code-execution surface and MUST stay disjoint from the MCP tool surface.
from hydra.services.console import VERIFICATION_COMMANDS


@dataclass
class PermissionDecision:
    allowed: bool
    reason: str = ""


def resolve_tool_permission(tool: dict[str, Any] | None) -> PermissionDecision:
    """Resolve allow/deny for one tool BEFORE any request reaches the server.

    A tool must be BOTH enabled AND explicitly ``permission == "allow"``; a
    missing/unknown tool, a disabled tool, or a tool left at the default deny
    short-circuits the call (HL-ASSIST-03).
    """
    if tool is None:
        return PermissionDecision(False, "unknown tool")
    if not tool.get("enabled", False):
        return PermissionDecision(False, "tool is not enabled")
    if tool.get("permission") != "allow":
        return PermissionDecision(False, "tool permission is deny")
    return PermissionDecision(True, "allowed")


def is_verification_surface(tool_name: str) -> bool:
    """True when a tool name collides with the verification allowlist (HL-TRUST-04)."""
    normalized = (tool_name or "").strip().lower()
    if normalized in {cmd.lower() for cmd in VERIFICATION_COMMANDS}:
        return True
    # Guard the fully-qualified forms too (e.g. "verify.build", "console:test").
    tail = normalized.replace("verification.", "").split(":")[-1].split(".")[-1]
    return tail in {cmd.lower() for cmd in VERIFICATION_COMMANDS}


def wrap_untrusted(text: str, *, seed: str = "") -> dict[str, Any]:
    """Wrap MCP tool output in the single delimited untrusted region (HL-TRUST-01)."""
    region = assemble_untrusted_region(text, provenance="untrusted-external")
    region["origin"] = "mcp-tool"
    return region


class McpTracePort(Protocol):
    """Run-trace sink for one MCP tool-call attempt.

    # RECONCILE-WITH-02-01: 02-01's run-trace store implements this port.
    """

    async def record_mcp_call_event(self, **event: Any) -> dict[str, Any]: ...
    async def store_mcp_artifact(self, *, event_id: str, tool_id: Any, content: str) -> dict[str, Any]: ...
