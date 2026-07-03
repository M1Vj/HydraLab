"""MCP orchestration: the single gated tool-call path (feature 02-02).

Every attempt flows through here so it cannot bypass the permission resolver,
the consent gate, the trace log, the untrusted-external artifact tag, or the
Review-Inbox routing of tool-derived write proposals.

# RECONCILE-WITH-02-01: the permission resolver (contracts.resolve_tool_permission)
# and the trace writer (Repository.record_mcp_call_event / store_mcp_artifact) are
# the thin local shim standing in for hydra.agents.* until 02-01 merges.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from hydra.services.assistant.consent import SendScopeItem, resolve_send_scope
from hydra.tools.mcp.client import MCPClient, MCPError, MCPToolResult, MCPTransport
from hydra.tools.mcp.connectors import get_connector_contract
from hydra.tools.mcp.contracts import (
    is_verification_surface,
    resolve_tool_permission,
    wrap_untrusted,
)

# Heuristic markers for tool output that *proposes* a state change. Detection
# only ROUTES a proposal to the Review Inbox; it never performs the write.
_WRITE_INTENT = re.compile(
    r"\b(save|store|create|add|update|write|promote|remember|claim|source|task|memory)\b",
    re.IGNORECASE,
)
_EXFIL_INTENT = re.compile(
    r"\b(email|send|exfiltrate|upload|post|leak|forward|transmit)\b.*\b(to|@)\b|@[\w.-]+\.\w+",
    re.IGNORECASE,
)

_MAX_SUMMARY = 240


@dataclass
class Privacy:
    """Outbound consent posture for an egressing MCP call (HL-TRUST-03)."""

    g3_enabled: bool = False
    offline_only: bool = False
    opt_ins: dict[str, bool] = field(default_factory=dict)
    ignored_paths: list[str] = field(default_factory=list)


@dataclass
class MCPCallResult:
    status: str  # allowed-completed | denied | error
    reason: str = ""
    event: dict[str, Any] | None = None
    artifact: dict[str, Any] | None = None
    untrusted_region: dict[str, Any] | None = None
    proposals: list[dict[str, Any]] = field(default_factory=list)
    excluded_content: list[dict[str, Any]] = field(default_factory=list)
    output: str = ""


def _summarize(text: str) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text[:_MAX_SUMMARY] + ("…" if len(text) > _MAX_SUMMARY else "")


def _redact(text: str) -> tuple[str, str]:
    """Redact secret-looking tokens from a summary; report what was redacted."""
    redactions: list[str] = []

    def _sub(pattern: str, label: str, value: str) -> str:
        nonlocal redactions
        new = re.sub(pattern, "[redacted]", value)
        if new != value:
            redactions.append(label)
        return new

    redacted = _sub(r"\b(sk-|ghp_|xox[bp]-|AKIA|ASIA)[A-Za-z0-9_\-]+", "api-key", text)
    redacted = _sub(r"[\w.+-]+@[\w.-]+\.\w+", "email", redacted)
    redacted = _sub(r"\bBearer\s+[A-Za-z0-9._\-]+", "bearer-token", redacted)
    return redacted, (", ".join(sorted(set(redactions))) or "none")


class MCPService:
    def __init__(self, repo: Any) -> None:
        # ``repo`` is a hydra.database.repository.Repository (duck-typed so tests
        # can inject a compatible stub).
        self.repo = repo

    # -------------------------------------------------------------- registry
    async def register_server(
        self,
        *,
        name: str,
        transport: str = "stdio",
        connection: Optional[dict[str, Any]] = None,
        auth_handle_ref: Optional[str] = None,
        connector: Optional[str] = None,
    ) -> dict[str, Any]:
        if transport == "http":
            url = str((connection or {}).get("url") or "")
            if url:
                # SSRF containment: an HTTP MCP server must be loopback-only, so a
                # non-loopback URL is rejected at registration (raises ValueError
                # -> 400) rather than being persisted and dialed later.
                from hydra.tools.mcp.client import assert_loopback_url

                assert_loopback_url(url)
        return await self.repo.register_mcp_server(
            name=name,
            transport=transport,
            connection=connection,
            auth_handle_ref=auth_handle_ref,
            connector=connector,
        )

    async def register_connector(self, connector_id: str, *, name: Optional[str] = None) -> dict[str, Any]:
        """Register a declared connector contract WITHOUT needing the app installed.

        The connector's static read-only tool list is persisted disabled; the
        Zotero contract therefore registers with zero write operations even when
        Zotero is absent (HL-ASSIST-08).
        """
        contract = get_connector_contract(connector_id)
        if contract is None:
            raise ValueError(f"unknown connector contract: {connector_id}")
        server = await self.repo.register_mcp_server(
            name=name or contract.name,
            transport=contract.transport,
            connection={"connector": contract.id},
            connector=contract.id,
        )
        for tool in contract.tools:
            await self.repo.upsert_mcp_tool(
                server_id=server["id"],
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
                read_only=tool.read_only,
            )
        return server

    async def connect_and_discover(self, server_id: str, transport: MCPTransport) -> dict[str, Any]:
        """Connect an enabled server and persist each discovered tool disabled.

        On unreachability the server flips to the ``failure`` state carrying the
        connection error string (HL-ASSIST-07); no tools are persisted.
        """
        server = await self.repo.get_mcp_server(server_id)
        if server is None:
            raise ValueError("server not found")
        if not server.get("enabled"):
            raise PermissionError("server is disabled; enable it before discovery")

        client = MCPClient(transport)
        try:
            # The transport speaks blocking HTTP; run it off the event loop so an
            # unreachable/slow server (up to the 5s timeout) can't stall the whole
            # backend for other requests.
            await asyncio.to_thread(client.connect)
            tools = await asyncio.to_thread(client.list_tools)
        except MCPError as exc:
            await self.repo.set_mcp_server_status(server_id, "failed", connection_error=str(exc))
            return {"status": "failed", "error": str(exc), "tools": []}

        persisted: list[dict[str, Any]] = []
        for tool in tools:
            persisted.append(
                await self.repo.upsert_mcp_tool(
                    server_id=server_id,
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    read_only=tool.read_only,
                )
            )
        await self.repo.set_mcp_server_status(server_id, "connected", connection_error="")
        return {"status": "connected", "tools": persisted}

    async def list_offered_tools(self) -> list[dict[str, Any]]:
        """Tools actually offered to the assistant: enabled AND allowed only.

        With no server configured (or none enabled/allowed) this is empty, so the
        assistant behaves exactly as the no-MCP path (HL-ASSIST-06).
        """
        servers = await self.repo.list_mcp_servers()
        enabled_server_ids = {s["id"] for s in servers if s.get("enabled")}
        offered: list[dict[str, Any]] = []
        for tool in await self.repo.list_mcp_tools(enabled_only=True):
            if tool.get("server_id") not in enabled_server_ids:
                continue
            if tool.get("permission") == "allow":
                offered.append(tool)
        return offered

    # ------------------------------------------------------------- invocation
    async def call_tool(
        self,
        tool_id: str,
        arguments: Optional[dict[str, Any]] = None,
        *,
        transport: Optional[MCPTransport] = None,
        egress_content: Optional[list[dict[str, Any]]] = None,
        privacy: Optional[Privacy] = None,
        route_proposals: bool = True,
    ) -> MCPCallResult:
        arguments = dict(arguments or {})
        tool = await self.repo.get_mcp_tool(tool_id)
        tool_name = (tool or {}).get("name", "")
        server_id = (tool or {}).get("server_id")

        # HL-TRUST-04: MCP can never reach the verification allowlist.
        if tool is not None and is_verification_surface(tool_name):
            return await self._deny(
                tool_id, server_id, tool_name,
                reason="MCP tools cannot reach the Section 26.6 verification allowlist",
            )

        # HL-ASSIST-03: resolve allow/deny BEFORE any request reaches the server.
        decision = resolve_tool_permission(tool)
        if not decision.allowed:
            return await self._deny(tool_id, server_id, tool_name, reason=decision.reason)

        # HL-TRUST-03: enforce consent gate + content-type filter on egress.
        excluded_content: list[dict[str, Any]] = []
        if egress_content:
            arguments, excluded_content = self._filter_egress(arguments, egress_content, privacy or Privacy())

        # Perform the call. A denied call never gets here, so only allowed calls
        # ever touch the transport.
        if transport is None:
            return await self._error(tool_id, server_id, tool_name, "no transport bound for this server")
        client = MCPClient(transport)
        try:
            # Blocking HTTP transport → run off the event loop (see discovery).
            await asyncio.to_thread(client.connect)
            result = await asyncio.to_thread(client.call_tool, tool_name, arguments)
        except MCPError as exc:
            return await self._error(tool_id, server_id, tool_name, str(exc))

        return await self._complete(
            tool_id, server_id, tool_name, arguments, result, excluded_content, route_proposals,
        )

    # ----------------------------------------------------------------- helpers
    def _filter_egress(
        self, arguments: dict[str, Any], egress_content: list[dict[str, Any]], privacy: Privacy
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        items = [
            SendScopeItem(
                ref_type=str(part.get("type") or "attachment"),
                id_or_path=str(part.get("id_or_path") or part.get("key") or ""),
                locator=dict(part.get("locator") or {}),
                label=str(part.get("label") or part.get("type") or ""),
            )
            for part in egress_content
        ]
        scope = resolve_send_scope(
            items,
            g3_enabled=privacy.g3_enabled,
            offline_only=privacy.offline_only,
            opt_ins=privacy.opt_ins,
            ignored_paths=privacy.ignored_paths,
        )
        included_keys = {(item["type"], item["id_or_path"]) for item in scope.included}
        excluded: list[dict[str, Any]] = []
        for part in egress_content:
            key = (str(part.get("type") or "attachment"), str(part.get("id_or_path") or part.get("key") or ""))
            arg_key = part.get("key")
            if key in included_keys and arg_key:
                arguments[arg_key] = part.get("text")
            else:
                # Excluded/blocked content NEVER reaches the outbound payload.
                if arg_key and arg_key in arguments:
                    arguments.pop(arg_key, None)
                reason = next(
                    (
                        x.get("reason")
                        for x in [*scope.excluded, *scope.blocked]
                        if (x["type"], x["id_or_path"]) == key
                    ),
                    "excluded by privacy settings",
                )
                excluded.append({"type": key[0], "content_type": part.get("type"), "reason": reason})
        return arguments, excluded

    async def _deny(self, tool_id, server_id, tool_name, *, reason: str) -> MCPCallResult:
        event = await self.repo.record_mcp_call_event(
            status="denied",
            tool_id=tool_id,
            server_id=server_id,
            tool_name=tool_name,
            request_summary="(call short-circuited before reaching the server)",
            output_summary="",
            redaction="none",
            detail=reason,
        )
        return MCPCallResult(status="denied", reason=reason, event=event)

    async def _error(self, tool_id, server_id, tool_name, detail: str) -> MCPCallResult:
        event = await self.repo.record_mcp_call_event(
            status="error",
            tool_id=tool_id,
            server_id=server_id,
            tool_name=tool_name,
            request_summary="(call attempted)",
            output_summary="",
            redaction="none",
            detail=detail,
        )
        return MCPCallResult(status="error", reason=detail, event=event)

    async def _complete(
        self, tool_id, server_id, tool_name, arguments, result: MCPToolResult,
        excluded_content, route_proposals: bool,
    ) -> MCPCallResult:
        request_summary, req_redaction = _redact(_summarize("args=" + ", ".join(sorted(arguments.keys()))))
        output_summary, out_redaction = _redact(_summarize(result.content))
        redaction = ", ".join(sorted({r for r in (req_redaction, out_redaction) if r and r != "none"})) or "none"

        event = await self.repo.record_mcp_call_event(
            status="allowed-completed",
            tool_id=tool_id,
            server_id=server_id,
            tool_name=tool_name,
            request_summary=request_summary,
            output_summary=output_summary,
            redaction=redaction,
            content_exclusions=excluded_content,
        )
        # HL-ASSIST-05: retain the full result as an untrusted-external artifact.
        artifact = await self.repo.store_mcp_artifact(
            event_id=event["id"], tool_id=tool_id, content=result.content
        )
        # HL-TRUST-01: tool output re-enters the model only as delimited data.
        region = wrap_untrusted(result.content, seed=event["id"])

        proposals: list[dict[str, Any]] = []
        if route_proposals:
            proposals = await self._route_proposals(tool_id, tool_name, result.content)

        return MCPCallResult(
            status="allowed-completed",
            event=event,
            artifact=artifact,
            untrusted_region=region,
            proposals=proposals,
            excluded_content=excluded_content,
            output=result.content,
        )

    async def _route_proposals(self, tool_id, tool_name: str, output: str) -> list[dict[str, Any]]:
        """Route any tool-derived candidate write to the Review Inbox (HL-TRUST-02).

        The MCP service has NO code path that applies a write from tool output;
        this only surfaces a reviewable proposal, tagged untrusted-external with
        its originating tool and an excerpt. Exfiltration-shaped instructions are
        recorded as blocked and reach no outbound recipient (HL-TRUST-05).
        """
        proposals: list[dict[str, Any]] = []
        excerpt = _summarize(output)
        is_exfil = bool(_EXFIL_INTENT.search(output or ""))
        is_write = bool(_WRITE_INTENT.search(output or ""))
        if not (is_exfil or is_write):
            return proposals

        disposition = "blocked" if is_exfil else "review-inbox"
        item = await self.repo.create_review_item(
            {
                "item_type": "untrusted-tool-proposal",
                "title": f"Untrusted MCP tool output proposed an action ({tool_name})",
                "summary": excerpt,
                "origin_type": "mcp_tool",
                "origin_id": tool_id,
                "payload": {
                    "trust_origin": "untrusted-external",
                    "origin_tool": tool_name,
                    "excerpt": excerpt,
                    "disposition": disposition,
                    "kind": "exfiltration" if is_exfil else "write-proposal",
                },
            }
        )
        proposals.append(
            {
                "review_item_id": item["id"],
                "disposition": disposition,
                "kind": "exfiltration" if is_exfil else "write-proposal",
                "origin_tool": tool_name,
                "excerpt": excerpt,
            }
        )
        return proposals
