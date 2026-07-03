import { afterEach, describe, expect, test } from "bun:test";

import { createApiClient } from "../../lib/api";
import type { McpServerInfo } from "../../lib/api";
import {
  deriveMcpPanelState,
  discoverMcpTools,
  enableMcpServer,
  registerMcpServer,
  setMcpToolPermission,
  toolStatusLabel,
} from "./mcpController";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function server(overrides: Partial<McpServerInfo> = {}): McpServerInfo {
  return {
    id: "s1",
    name: "Context7",
    transport: "http",
    enabled: true,
    connector: null,
    status: "connected",
    connection_error: "",
    auth_handle_ref: null,
    state: "ready",
    tools: [],
    ...overrides,
  };
}

describe("deriveMcpPanelState — four defined states, never blank", () => {
  test("loading while discovery is in flight", () => {
    expect(deriveMcpPanelState([], true).state).toBe("loading");
  });

  test("empty when no server configured, with a connect prompt", () => {
    const view = deriveMcpPanelState([]);
    expect(view.state).toBe("empty");
    expect(view.message.length).toBeGreaterThan(0);
  });

  test("failure surfaces the connection error string", () => {
    const view = deriveMcpPanelState([server({ status: "failed", state: "failure", connection_error: "ECONNREFUSED 127.0.0.1:23119" })]);
    expect(view.state).toBe("failure");
    expect(view.errorDetail).toBe("ECONNREFUSED 127.0.0.1:23119");
  });

  test("permission-denied when tools exist but none is enabled+allowed", () => {
    const view = deriveMcpPanelState([
      server({ tools: [{ id: "t1", name: "navigate", description: "", enabled: false, permission: "deny", read_only: false, status: "disabled" }] }),
    ]);
    expect(view.state).toBe("permission-denied");
  });

  test("ready when at least one tool is enabled and allowed", () => {
    const view = deriveMcpPanelState([
      server({ tools: [{ id: "t1", name: "navigate", description: "", enabled: true, permission: "allow", read_only: false, status: "allowed" }] }),
    ]);
    expect(view.state).toBe("ready");
  });
});

describe("tool status label", () => {
  test("allowed only when enabled and permission allow", () => {
    expect(toolStatusLabel({ id: "t", name: "n", description: "", enabled: true, permission: "allow", read_only: false, status: "allowed" })).toBe("allowed");
    expect(toolStatusLabel({ id: "t", name: "n", description: "", enabled: true, permission: "deny", read_only: false, status: "disabled" })).toBe("disabled");
    expect(toolStatusLabel({ id: "t", name: "n", description: "", enabled: false, permission: "allow", read_only: false, status: "disabled" })).toBe("disabled");
  });
});

describe("mcp controller requests", () => {
  test("register posts the connector body", async () => {
    let captured: { url: string; body: unknown } | null = null;
    globalThis.fetch = async (input, init) => {
      captured = { url: String(input), body: JSON.parse(String(init?.body ?? "{}")) };
      return jsonResponse({ server: server({ connector: "zotero-local" }) });
    };
    const client = createApiClient("/api", 100);
    await registerMcpServer({ name: "Zotero", connector: "zotero-local" }, client);
    expect(captured!.url).toContain("/api/mcp/servers");
    expect(captured!.body).toEqual({ name: "Zotero", connector: "zotero-local" });
  });

  test("enable hits the enable route with the flag", async () => {
    let captured: { url: string; body: unknown } | null = null;
    globalThis.fetch = async (input, init) => {
      captured = { url: String(input), body: JSON.parse(String(init?.body ?? "{}")) };
      return jsonResponse({ server: server() });
    };
    const client = createApiClient("/api", 100);
    await enableMcpServer("s1", true, client);
    expect(captured!.url).toContain("/api/mcp/servers/s1/enable");
    expect(captured!.body).toEqual({ enabled: true });
  });

  test("discover posts to the discover route", async () => {
    let capturedUrl = "";
    globalThis.fetch = async (input) => {
      capturedUrl = String(input);
      return jsonResponse({ result_status: "connected", server: server() });
    };
    const client = createApiClient("/api", 100);
    await discoverMcpTools("s1", client);
    expect(capturedUrl).toContain("/api/mcp/servers/s1/discover");
  });

  test("tool permission patch sends enabled + permission", async () => {
    let captured: { url: string; body: unknown } | null = null;
    globalThis.fetch = async (input, init) => {
      captured = { url: String(input), body: JSON.parse(String(init?.body ?? "{}")) };
      return jsonResponse({ tool: { id: "t1", name: "navigate", description: "", enabled: true, permission: "allow", read_only: false, status: "allowed" } });
    };
    const client = createApiClient("/api", 100);
    await setMcpToolPermission("t1", { enabled: true, permission: "allow" }, client);
    expect(captured!.url).toContain("/api/mcp/tools/t1");
    expect(captured!.body).toEqual({ enabled: true, permission: "allow" });
  });
});
