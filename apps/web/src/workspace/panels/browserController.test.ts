import { afterEach, describe, expect, test } from "bun:test";

import { createApiClient } from "../../lib/api";
import {
  BROWSER_MODES,
  browserActionLogState,
  groupBrowserTabs,
  listBrowserActions,
  listBrowserActionLog,
  setBrowserHostPermission,
  type BrowserActionLogEntry,
  type BrowserTab,
} from "./browserController";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("browser mode selector", () => {
  test("offers Passive and Co-pilot only", () => {
    expect(BROWSER_MODES.map((mode) => mode.id)).toEqual(["passive", "copilot"]);
    expect(BROWSER_MODES.map((mode) => mode.id)).not.toContain("full_access" as never);
    expect(BROWSER_MODES.map((mode) => mode.id)).not.toContain("autopilot" as never);
  });
});

describe("browser action log states", () => {
  test("renders empty/loading/failure/permission-denied/ready states", () => {
    expect(browserActionLogState({ loading: true, error: null, permissionDenied: false, actions: [] }).state).toBe("loading");
    expect(browserActionLogState({ loading: false, error: null, permissionDenied: false, actions: [] }).state).toBe("empty");
    expect(browserActionLogState({ loading: false, error: new Error("boom"), permissionDenied: false, actions: [] }).state).toBe("failure");
    expect(browserActionLogState({ loading: false, error: null, permissionDenied: true, actions: [] }).state).toBe("permission-denied");
    expect(browserActionLogState({ loading: false, error: null, permissionDenied: false, actions: [logEntry()] }).state).toBe("ready");
  });
});

describe("task tab grouping", () => {
  test("groups tabs by research task label", () => {
    const tabs: BrowserTab[] = [
      { id: "tab-1", title: "Attention", url: "https://arxiv.org/abs/1706.03762", task_group_id: "transformer", task_group_label: "Transformer survey" },
      { id: "tab-2", title: "BERT", url: "https://arxiv.org/abs/1810.04805", task_group_id: "transformer", task_group_label: "Transformer survey" },
      { id: "tab-3", title: "DDPM", url: "https://arxiv.org/abs/2006.11239", task_group_id: "diffusion", task_group_label: "Diffusion survey" },
    ];
    const groups = groupBrowserTabs(tabs);
    expect(groups[0]).toMatchObject({ id: "transformer", label: "Transformer survey" });
    expect(groups[0].tabs).toHaveLength(2);
    expect(groups[1]).toMatchObject({ id: "diffusion", label: "Diffusion survey" });
  });
});

describe("browser controller requests", () => {
  test("loads action descriptors with host", async () => {
    let capturedUrl = "";
    globalThis.fetch = async (input) => {
      capturedUrl = String(input);
      return jsonResponse({ actions: [{ name: "browser.save-source", verb: "Save source", host: "arxiv.org" }] });
    };
    const client = createApiClient("/api", 100);
    const result = await listBrowserActions("arxiv.org", client);
    expect(capturedUrl).toContain("/api/browser/actions?host=arxiv.org");
    expect(result.actions[0].verb).toBe("Save source");
  });

  test("sets four-state host permission", async () => {
    let captured: { url: string; body: unknown } | null = null;
    globalThis.fetch = async (input, init) => {
      captured = { url: String(input), body: JSON.parse(String(init?.body ?? "{}")) };
      return jsonResponse({ permission: { project_id: "default", host: "arxiv.org", state: "always_allow_host" } });
    };
    const client = createApiClient("/api", 100);
    await setBrowserHostPermission("default", "arxiv.org", "always_allow_host", client);
    expect(captured!.url).toContain("/api/browser/permissions");
    expect(captured!.body).toEqual({ project_id: "default", host: "arxiv.org", state: "always_allow_host" });
  });

  test("loads append-only action log", async () => {
    globalThis.fetch = async () => jsonResponse({ actions: [logEntry()] });
    const client = createApiClient("/api", 100);
    const result = await listBrowserActionLog("default", client);
    expect(result.actions[0].approval_result).toBe("approved");
  });
});

function logEntry(overrides: Partial<BrowserActionLogEntry> = {}): BrowserActionLogEntry {
  return {
    id: "log-1",
    project_id: "default",
    action: "save-source",
    host: "arxiv.org",
    mode: "copilot",
    approval_result: "approved",
    timestamp: "2026-07-02T08:00:00+00:00",
    ...overrides,
  };
}
