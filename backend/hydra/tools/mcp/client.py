"""HydraLab-owned MCP client abstraction (HL-ASSIST-01/02, Section 25.7).

HydraLab does not vendor the MCP Python SDK; it speaks the MCP request/response
shape (``initialize`` / ``tools/list`` / ``tools/call``) over a pluggable
transport so a fake in-process server can drive the exact same code path as a
real stdio/HTTP server, and so no third-party (potentially non-permissive)
dependency is pulled in. No transport credentials are hard-coded here; the
caller supplies a resolved connection dict + an optional auth handle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class MCPError(Exception):
    """Raised when the MCP transport or server reports a protocol-level error."""


@dataclass
class MCPToolDescriptor:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    # A connector contract may advertise a tool as read-only (HL-ASSIST-08).
    read_only: bool = False


@dataclass
class MCPToolResult:
    """Result of a ``tools/call``. ``content`` is the concatenated text output.

    Everything a server returns is untrusted-external data (DEC-11); the client
    never interprets it as an instruction.
    """

    content: str = ""
    is_error: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class MCPTransport(Protocol):
    """Minimal MCP transport: a single request/response round-trip.

    A real transport frames JSON-RPC over stdio or HTTP; the fake test transport
    dispatches in-process. Either way it returns the ``result`` object (or raises
    :class:`MCPError`).
    """

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]: ...


class MCPClient:
    """Connect / list-tools / call-tool over an injected transport."""

    def __init__(self, transport: MCPTransport) -> None:
        self._transport = transport
        self._connected = False

    def connect(self) -> dict[str, Any]:
        """Perform the MCP ``initialize`` handshake."""
        try:
            info = self._transport.request("initialize", {"protocolVersion": "2024-11-05"})
        except MCPError:
            raise
        except Exception as exc:  # transport-level failure -> surfaced as connection error
            raise MCPError(str(exc)) from exc
        self._connected = True
        return info or {}

    def list_tools(self) -> list[MCPToolDescriptor]:
        if not self._connected:
            raise MCPError("client is not connected; call connect() first")
        result = self._transport.request("tools/list", {})
        tools: list[MCPToolDescriptor] = []
        for entry in (result or {}).get("tools", []) or []:
            tools.append(
                MCPToolDescriptor(
                    name=str(entry.get("name") or ""),
                    description=str(entry.get("description") or ""),
                    input_schema=dict(entry.get("inputSchema") or entry.get("input_schema") or {}),
                    read_only=bool(entry.get("readOnly") or entry.get("read_only") or False),
                )
            )
        return [t for t in tools if t.name]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPToolResult:
        if not self._connected:
            raise MCPError("client is not connected; call connect() first")
        result = self._transport.request("tools/call", {"name": name, "arguments": arguments or {}})
        result = result or {}
        content = _flatten_content(result.get("content"))
        return MCPToolResult(content=content, is_error=bool(result.get("isError")), raw=result)


class HttpMCPTransport:
    """JSON-RPC-over-HTTP transport for a local MCP server (127.0.0.1 only).

    Streaming MCP transports (stdio) are out of scope for this branch; this
    covers connectors that expose a local HTTP endpoint. Any transport error
    surfaces as :class:`MCPError`, which drives the Settings ``failure`` state.
    """

    def __init__(self, url: str, *, auth_token: str | None = None, timeout: float = 5.0) -> None:
        self._url = url
        self._auth_token = auth_token
        self._timeout = timeout
        self._id = 0

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        import httpx

        if not self._url:
            raise MCPError("no MCP server URL configured")
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        headers = {"content-type": "application/json"}
        if self._auth_token:
            headers["authorization"] = f"Bearer {self._auth_token}"
        try:
            response = httpx.post(self._url, json=payload, headers=headers, timeout=self._timeout)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:  # network/protocol failure -> connection error
            raise MCPError(f"MCP server unreachable: {exc}") from exc
        if isinstance(body, dict) and body.get("error"):
            raise MCPError(str(body["error"]))
        return (body or {}).get("result", {}) if isinstance(body, dict) else {}


def _flatten_content(content: Any) -> str:
    """MCP tool content is a list of typed parts; concatenate the text parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                if part.get("type") in (None, "text") and "text" in part:
                    parts.append(str(part.get("text") or ""))
                elif "text" in part:
                    parts.append(str(part.get("text") or ""))
            else:
                parts.append(str(part))
    else:
        parts.append(str(content))
    return "\n".join(p for p in parts if p)
