import { api, type ApiClient, type McpServerInfo, type McpServersResponse, type McpToolInfo } from "../../lib/api";

export type McpPanelState = "empty" | "loading" | "failure" | "permission-denied" | "ready";

export type McpPanelView = {
  state: McpPanelState;
  message: string;
  errorDetail?: string;
};

/**
 * Derive the panel state (HL-ASSIST-07). No state ever renders a blank panel:
 * every branch carries visible content.
 *   - loading: discovery in flight
 *   - empty: no server configured
 *   - failure: a server is unreachable (surface its connection error string)
 *   - permission-denied: tools exist but none is enabled+allowed
 *   - ready: at least one tool is enabled and allowed
 */
export function deriveMcpPanelState(servers: McpServerInfo[], loading = false): McpPanelView {
  if (loading) {
    return { state: "loading", message: "Discovering tools…" };
  }
  if (servers.length === 0) {
    return { state: "empty", message: "No MCP server connected. Connect a server to discover tools." };
  }
  const failed = servers.find((server) => server.status === "failed" || server.state === "failure");
  if (failed) {
    return {
      state: "failure",
      message: `Could not reach “${failed.name}”.`,
      errorDetail: failed.connection_error || "Connection failed.",
    };
  }
  const anyAllowed = servers.some((server) => server.tools.some((tool) => tool.enabled && tool.permission === "allow"));
  if (!anyAllowed) {
    return {
      state: "permission-denied",
      message: "Discovered tools are disabled. Enable a tool to allow the assistant to call it.",
    };
  }
  return { state: "ready", message: "MCP tools ready." };
}

export function toolStatusLabel(tool: McpToolInfo): string {
  if (tool.enabled && tool.permission === "allow") return "allowed";
  return "disabled";
}

export function listMcpServers(client: ApiClient = api): Promise<McpServersResponse> {
  return client.get<McpServersResponse>("/api/mcp/servers");
}

export function registerMcpServer(
  input: { name: string; transport?: string; connection?: Record<string, unknown>; auth_handle_ref?: string | null; connector?: string | null },
  client: ApiClient = api,
): Promise<{ server: McpServerInfo }> {
  return client.post<{ server: McpServerInfo }>("/api/mcp/servers", input);
}

export function enableMcpServer(serverId: string, enabled: boolean, client: ApiClient = api): Promise<{ server: McpServerInfo }> {
  return client.post<{ server: McpServerInfo }>(`/api/mcp/servers/${encodeURIComponent(serverId)}/enable`, { enabled });
}

export function discoverMcpTools(serverId: string, client: ApiClient = api): Promise<{ result_status: string; server: McpServerInfo }> {
  return client.post<{ result_status: string; server: McpServerInfo }>(`/api/mcp/servers/${encodeURIComponent(serverId)}/discover`);
}

export function setMcpToolPermission(
  toolId: string,
  input: { enabled?: boolean; permission?: "allow" | "deny" },
  client: ApiClient = api,
): Promise<{ tool: McpToolInfo }> {
  return client.patch<{ tool: McpToolInfo }>(`/api/mcp/tools/${encodeURIComponent(toolId)}`, input);
}
