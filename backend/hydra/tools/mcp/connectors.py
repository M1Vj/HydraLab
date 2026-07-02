"""Connector contracts for MCP servers (HL-ASSIST-08, Section 25.7).

A connector contract is a HydraLab-declared descriptor of a well-known MCP
server. It can be *registered* (its read-only tool surface persisted) without
the underlying app being installed, because the declared tool list is static.
The flagship contract is the Zotero local connector: read-only, zero write
operations, no Phase-2 write-back.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from hydra.tools.mcp.client import MCPToolDescriptor


@dataclass
class ConnectorContract:
    id: str
    name: str
    transport: str
    read_only: bool
    tools: list[MCPToolDescriptor] = field(default_factory=list)

    def write_operations(self) -> list[str]:
        """Names of any write-capable tools. Read-only connectors return []."""
        if self.read_only:
            return []
        return [t.name for t in self.tools if not t.read_only]


# Zotero local read-only connector contract. Every declared tool is read-only;
# there is NO write path (no create/update/delete item) in Phase 2. The contract
# is static so it registers whether or not Zotero is installed/running.
ZOTERO_LOCAL_CONNECTOR = ConnectorContract(
    id="zotero-local",
    name="Zotero (local, read-only)",
    transport="http",  # Zotero local HTTP API on 127.0.0.1:23119, when present
    read_only=True,
    tools=[
        MCPToolDescriptor(
            name="list_library_items",
            description="List items in the local Zotero library (read-only).",
            input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
            read_only=True,
        ),
        MCPToolDescriptor(
            name="get_item",
            description="Fetch a single Zotero item by key (read-only).",
            input_schema={"type": "object", "properties": {"item_key": {"type": "string"}}, "required": ["item_key"]},
            read_only=True,
        ),
        MCPToolDescriptor(
            name="search_items",
            description="Search the local Zotero library (read-only).",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            read_only=True,
        ),
        MCPToolDescriptor(
            name="list_collections",
            description="List Zotero collections (read-only).",
            input_schema={"type": "object", "properties": {}},
            read_only=True,
        ),
    ],
)


CONNECTOR_CONTRACTS: dict[str, ConnectorContract] = {
    ZOTERO_LOCAL_CONNECTOR.id: ZOTERO_LOCAL_CONNECTOR,
}


def get_connector_contract(connector_id: str) -> ConnectorContract | None:
    return CONNECTOR_CONTRACTS.get(connector_id)
