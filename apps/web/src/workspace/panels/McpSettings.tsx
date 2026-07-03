import { useCallback, useEffect, useState } from "react";
import { Plug, ShieldAlert } from "lucide-react";
import type { McpServerInfo } from "../../lib/api";
import {
  deriveMcpPanelState,
  discoverMcpTools,
  enableMcpServer,
  listMcpServers,
  registerMcpServer,
  setMcpToolPermission,
} from "./mcpController";

/**
 * MCP settings surface (HL-ASSIST-07). Renders four defined states —
 * empty / loading / failure / permission-denied — and never a blank panel.
 * Every control is keyboard-focusable (buttons + checkboxes).
 */
export function McpSettingsSection() {
  const [servers, setServers] = useState<McpServerInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await listMcpServers();
      setServers(payload.servers);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load MCP servers");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const view = deriveMcpPanelState(servers, loading);

  async function connectZotero() {
    setBusy(true);
    try {
      await registerMcpServer({ name: "Zotero (local, read-only)", connector: "zotero-local" });
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function toggleServer(server: McpServerInfo) {
    setBusy(true);
    try {
      await enableMcpServer(server.id, !server.enabled);
      if (!server.enabled) await discoverMcpTools(server.id).catch(() => undefined);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function retryDiscovery(server: McpServerInfo) {
    setBusy(true);
    try {
      await discoverMcpTools(server.id).catch(() => undefined);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function toggleTool(toolId: string, enabled: boolean) {
    setBusy(true);
    try {
      await setMcpToolPermission(toolId, { enabled, permission: enabled ? "allow" : "deny" });
      await load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="settings-section" aria-label="MCP tools">
      <header>
        <Plug size={15} />
        <strong>MCP tools</strong>
      </header>

      {view.state === "loading" && (
        <p className="settings-hint" role="status" aria-live="polite">
          {view.message}
        </p>
      )}

      {view.state === "empty" && (
        <div className="mcp-empty">
          <p className="settings-hint">{view.message}</p>
          <button type="button" disabled={busy} onClick={() => void connectZotero()}>
            Connect Zotero (read-only)
          </button>
        </div>
      )}

      {view.state !== "loading" && view.state !== "empty" && (
        <>
          {view.state === "failure" && (
            <p className="inspector-error" role="alert">
              <ShieldAlert size={12} /> {view.message} {view.errorDetail}
            </p>
          )}
          {view.state === "permission-denied" && (
            <p className="settings-hint" role="status">
              {view.message}
            </p>
          )}
          <ul className="mcp-server-list">
            {servers.map((server) => (
              <li key={server.id} className={`mcp-server mcp-state-${server.state}`}>
                <div className="mcp-server-head">
                  <strong>{server.name}</strong>
                  <span className="mcp-server-status">{server.status}</span>
                  <label className="mcp-server-toggle">
                    <input
                      type="checkbox"
                      checked={server.enabled}
                      disabled={busy}
                      onChange={() => void toggleServer(server)}
                    />
                    enabled
                  </label>
                </div>
                {server.status === "failed" && (
                  <div className="mcp-server-failure">
                    <span className="inspector-error" role="alert">
                      {server.connection_error || "Connection failed."}
                    </span>
                    <button type="button" disabled={busy} onClick={() => void retryDiscovery(server)}>
                      Retry
                    </button>
                  </div>
                )}
                {server.tools.length === 0 ? (
                  <span className="settings-hint">No tools discovered yet.</span>
                ) : (
                  <ul className="mcp-tool-list">
                    {server.tools.map((tool) => (
                      <li key={tool.id} className={`mcp-tool mcp-tool-${tool.status}`}>
                        <label>
                          <input
                            type="checkbox"
                            checked={tool.enabled && tool.permission === "allow"}
                            disabled={busy}
                            onChange={(event) => void toggleTool(tool.id, event.target.checked)}
                          />
                          <span className="mcp-tool-name">{tool.name}</span>
                        </label>
                        <span className="mcp-tool-meta">
                          {tool.read_only && <span className="mcp-readonly">read-only</span>}
                          <span className="mcp-tool-status">{tool.status}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {error && (
        <p className="inspector-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
