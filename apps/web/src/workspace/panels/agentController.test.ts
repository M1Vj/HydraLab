import { describe, expect, test } from "bun:test";
import {
  AGENT_ACCESS_MODES,
  isFlaggedStep,
  isModeSelectable,
  modeLabel,
  resolveApproval,
  setFullAccess,
  setMode,
} from "./agentController";
import type { ApiClient, AssistantModes } from "../../lib/api";

function fakeClient(handler: (path: string, body?: unknown) => unknown): ApiClient {
  return {
    get: async <T,>(path: string) => handler(path) as T,
    post: async <T,>(path: string, body?: unknown) => handler(path, body) as T,
    put: async <T,>(path: string, body?: unknown) => handler(path, body) as T,
    patch: async <T,>(path: string, body?: unknown) => handler(path, body) as T,
    delete: async <T,>(path: string) => handler(path) as T,
    stream: async () => undefined,
  } as unknown as ApiClient;
}

describe("agent access mode", () => {
  test("exactly three canonical modes exist", () => {
    expect(AGENT_ACCESS_MODES).toEqual(["passive", "copilot", "full_access"]);
    expect(AGENT_ACCESS_MODES).not.toContain("autopilot" as never);
  });

  test("mode labels map ids to human copy", () => {
    expect(modeLabel("passive")).toContain("Passive");
    expect(modeLabel("copilot")).toContain("Co-pilot");
    expect(modeLabel("unknown")).toBe("unknown");
  });

  test("full access is not selectable until enabled for the project", () => {
    const modes: AssistantModes = {
      default_mode: "passive",
      full_access_enabled: false,
      offline_only: false,
      g3_provider_send: false,
      modes: [
        { id: "passive", label: "Passive", enabled: true, phase: 1 },
        { id: "copilot", label: "Co-pilot", enabled: true, phase: 2 },
        { id: "full_access", label: "Full Access", enabled: false, phase: 2 },
      ],
    };
    expect(isModeSelectable(modes, "copilot")).toBe(true);
    expect(isModeSelectable(modes, "full_access")).toBe(false);
  });

  test("setMode posts the chosen mode", async () => {
    const captured: { path: string; body: unknown } = { path: "", body: null };
    const client = fakeClient((path, body) => {
      captured.path = path;
      captured.body = body;
      return { default_mode: "copilot", full_access_enabled: false };
    });
    const result = await setMode("copilot", "default", client);
    expect(captured.path).toBe("/api/assistant/mode");
    expect(captured.body).toEqual({ mode: "copilot", project_id: "default" });
    expect(result.default_mode).toBe("copilot");
  });

  test("setFullAccess posts the per-project opt-in", async () => {
    const captured: { body: unknown } = { body: null };
    const client = fakeClient((_path, body) => {
      captured.body = body;
      return { full_access_enabled: true, default_mode: "passive" };
    });
    await setFullAccess(true, "default", client);
    expect(captured.body).toEqual({ enabled: true, project_id: "default" });
  });
});

describe("approvals", () => {
  test("resolveApproval posts the decision", async () => {
    const captured: { path: string; body: unknown } = { path: "", body: null };
    const client = fakeClient((path, body) => {
      captured.path = path;
      captured.body = body;
      return { applied: false, status: "rejected" };
    });
    const result = await resolveApproval("ap1", "rejected", client);
    expect(captured.path).toBe("/api/agent/approvals/ap1/resolve");
    expect(captured.body).toEqual({ decision: "rejected" });
    expect(result.applied).toBe(false);
  });
});

describe("trace flags", () => {
  test("denied capability and untrusted origin flag a step", () => {
    expect(isFlaggedStep({ trust_origin: "user", denied_capability: "send-email" })).toBe(true);
    expect(isFlaggedStep({ trust_origin: "untrusted-external" })).toBe(true);
    expect(isFlaggedStep({ trust_origin: "user" })).toBe(false);
  });
});
