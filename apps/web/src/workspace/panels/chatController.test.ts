import { describe, expect, test } from "bun:test";
import {
  buildContextRefs,
  initialStreamState,
  isConsentBlocked,
  reduceStreamEvent,
  previewSendScope,
} from "./chatController";
import type { ApiClient, SendScopeResult } from "../../lib/api";

describe("chat stream reducer", () => {
  test("accumulates streamed message deltas", () => {
    let state = initialStreamState("chat-1");
    state = reduceStreamEvent(state, { type: "status", content: "assembling context..." });
    state = reduceStreamEvent(state, { type: "message", content: "Hello " });
    state = reduceStreamEvent(state, { type: "message", content: "world" });
    state = reduceStreamEvent(state, { type: "done", chat_id: "chat-1", message_id: "m1" });
    expect(state.assistantContent).toBe("Hello world");
    expect(state.status).toBe("done");
    expect(state.messageId).toBe("m1");
  });

  test("offline-blocked event yields consent-blocked state", () => {
    let state = initialStreamState();
    state = reduceStreamEvent(state, { type: "blocked", reason: "offline-only mode blocks all provider sends", status: "offline-blocked" });
    expect(state.status).toBe("blocked");
    expect(isConsentBlocked(state)).toBe(true);
    expect(state.blockedReason).toContain("offline-only");
  });

  test("hard-blocked event is consent-blocked", () => {
    let state = initialStreamState();
    state = reduceStreamEvent(state, { type: "blocked", reason: ".env is a hard-blocked category", status: "hard-blocked" });
    expect(isConsentBlocked(state)).toBe(true);
  });

  test("budget event surfaces a non-consent block", () => {
    let state = initialStreamState();
    state = reduceStreamEvent(state, { type: "budget", reason: "token budget exceeded", status: "budget-exceeded" });
    expect(state.status).toBe("blocked");
    expect(isConsentBlocked(state)).toBe(false);
  });

  test("error event sets error status", () => {
    let state = initialStreamState();
    state = reduceStreamEvent(state, { type: "error", reason: "provider failed" });
    expect(state.status).toBe("error");
  });
});

describe("context refs", () => {
  test("builds refs from picker selections and drops empties", () => {
    const refs = buildContextRefs([
      { type: "source", id_or_path: "Attention Is All You Need" },
      { type: "", id_or_path: "" },
      { type: "active_file", id_or_path: "drafts/intro.md", label: "intro" },
    ]);
    expect(refs).toHaveLength(2);
    expect(refs[0].type).toBe("source");
    expect(refs[1].label).toBe("intro");
  });
});

describe("pre-send surface", () => {
  test("previewSendScope calls the send-scope endpoint", async () => {
    const captured: { path: string; body: unknown } = { path: "", body: null };
    const fake = {
      post: async <T,>(path: string, body?: unknown): Promise<T> => {
        captured.path = path;
        captured.body = body;
        return { included: [{ type: "active_file", id_or_path: "a.md" }], excluded: [], blocked: [] } as T;
      },
    } as unknown as ApiClient;
    const result: SendScopeResult = await previewSendScope([{ type: "active_file", id_or_path: "a.md" }], fake);
    expect(captured.path).toBe("/api/assistant/send-scope");
    expect(result.included).toHaveLength(1);
  });
});
