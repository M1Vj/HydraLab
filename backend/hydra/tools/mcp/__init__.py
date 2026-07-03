"""MCP tool integration (feature 02-02, Section 25.7 / 34).

This subsystem is Phase 2. ``MCP_SUBSYSTEM_PHASE`` marks it so a Phase-1 build
gate can confirm MCP is absent (HL-ASSIST-06); it defaults to disabled until a
server is configured, and with no server configured the assistant behaves
exactly as the no-MCP path.
"""
from __future__ import annotations

from hydra.tools.mcp.client import (
    MCPClient,
    MCPError,
    MCPToolDescriptor,
    MCPToolResult,
    MCPTransport,
)
from hydra.tools.mcp.connectors import (
    CONNECTOR_CONTRACTS,
    ZOTERO_LOCAL_CONNECTOR,
    ConnectorContract,
    get_connector_contract,
)
from hydra.tools.mcp.contracts import (
    PermissionDecision,
    is_verification_surface,
    resolve_tool_permission,
    wrap_untrusted,
)
from hydra.tools.mcp.service import MCPCallResult, MCPService, Privacy

MCP_SUBSYSTEM_PHASE = 2

__all__ = [
    "MCP_SUBSYSTEM_PHASE",
    "MCPClient",
    "MCPError",
    "MCPToolDescriptor",
    "MCPToolResult",
    "MCPTransport",
    "CONNECTOR_CONTRACTS",
    "ZOTERO_LOCAL_CONNECTOR",
    "ConnectorContract",
    "get_connector_contract",
    "PermissionDecision",
    "is_verification_surface",
    "resolve_tool_permission",
    "wrap_untrusted",
    "MCPCallResult",
    "MCPService",
    "Privacy",
]
