import { afterEach, describe, expect, test } from "bun:test";

import { createApiClient } from "../../lib/api";
import {
  approveDisabledReason,
  approveSelfEvolutionChange,
  canApprove,
  denySelfEvolutionChange,
  fetchSelfEvolutionAudit,
  listSelfEvolutionChanges,
  riskBadge,
  trustBadge,
  type SelfEvolutionChange,
} from "./selfEvolutionController";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const change = (over: Partial<SelfEvolutionChange> = {}): SelfEvolutionChange => ({
  id: "row-1",
  change_id: "chg-1",
  changeset_id: "cs-1",
  project_id: "default",
  run_id: null,
  category: "prompt",
  target_path: "skills/citation-check.md",
  unified_diff: "@@\n+Check each citation.\n",
  test_plan: ["bun run typecheck"],
  risk_class: "auto_eligible",
  risk_reason: "",
  trust_level: "user",
  origin: "user",
  status: "proposed",
  checkpoint_ref: null,
  verification_result: "",
  review_inbox: false,
  created_at: 0,
  updated_at: 0,
  ...over,
});

describe("approval gating (HL-ASSIST-31/32, HL-TRUST-20/21)", () => {
  test("a proposed, trusted, auto-eligible change with a test plan can be approved", () => {
    expect(canApprove(change())).toBe(true);
    expect(approveDisabledReason(change())).toBeNull();
  });

  test("an empty test plan is not approvable", () => {
    const c = change({ test_plan: [] });
    expect(canApprove(c)).toBe(false);
    expect(approveDisabledReason(c)).toContain("test plan is required");
  });

  test("a protected-field (review_required) change is not approvable", () => {
    const c = change({ risk_class: "review_required" });
    expect(canApprove(c)).toBe(false);
    expect(approveDisabledReason(c)).toContain("Review Inbox");
    expect(riskBadge(c).tone).toBe("danger");
  });

  test("an untrusted-external change is not approvable", () => {
    const c = change({ trust_level: "untrusted-external" });
    expect(canApprove(c)).toBe(false);
    expect(trustBadge(c).tone).toBe("danger");
  });

  test("an already-applied change is not re-approvable", () => {
    expect(canApprove(change({ status: "applied" }))).toBe(false);
  });
});

describe("self-evolution endpoints", () => {
  test("list hits the changes route with the project id", async () => {
    let capturedUrl = "";
    globalThis.fetch = async (input) => {
      capturedUrl = String(input);
      return jsonResponse({ changes: [] });
    };
    const client = createApiClient("/api", 100);
    await listSelfEvolutionChanges("transformer-survey", client);
    expect(capturedUrl).toBe("/api/self-evolution/changes?project_id=transformer-survey");
  });

  test("approve and deny post to the per-change routes", async () => {
    const urls: string[] = [];
    globalThis.fetch = async (input, init) => {
      urls.push(String(input));
      const body = JSON.parse(String(init?.body ?? "{}"));
      expect(body).toEqual({ actor: "user" });
      return jsonResponse({ change: change({ status: String(input).includes("approve") ? "applied" : "denied" }) });
    };
    const client = createApiClient("/api", 100);
    const approved = await approveSelfEvolutionChange("chg-1", client);
    const denied = await denySelfEvolutionChange("chg-2", client);
    expect(approved.change.status).toBe("applied");
    expect(denied.change.status).toBe("denied");
    expect(urls).toEqual([
      "/api/self-evolution/changes/chg-1/approve",
      "/api/self-evolution/changes/chg-2/deny",
    ]);
  });

  test("audit history hits the audit route", async () => {
    let capturedUrl = "";
    globalThis.fetch = async (input) => {
      capturedUrl = String(input);
      return jsonResponse({ entries: [] });
    };
    const client = createApiClient("/api", 100);
    await fetchSelfEvolutionAudit("default", client);
    expect(capturedUrl).toBe("/api/self-evolution/audit?project_id=default");
  });
});
