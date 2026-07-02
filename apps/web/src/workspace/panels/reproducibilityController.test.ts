import { describe, expect, test } from "bun:test";
import type { ReproducibilityPreviewResponse, ReproducibilityRunSummary } from "../../lib/api";
import {
  buildBundleRequest,
  canBuildBundle,
  includedCategoryLabels,
  reviewRedactionCount,
} from "./reproducibilityController";

const runs: ReproducibilityRunSummary[] = [
  {
    id: "run-2026-06-20-attention-replication",
    kind: "agent",
    label: "Attention replication",
    status: "completed",
    created_at: 1,
  },
];

const preview: ReproducibilityPreviewResponse = {
  status: "preview",
  project_id: "default",
  run_ids: ["run-2026-06-20-attention-replication"],
  included_categories: [
    { id: "sources", label: "Sources", count: 1 },
    { id: "artifacts", label: "Artifacts", count: 2 },
    { id: "ledger", label: "Ledger", count: 1 },
  ],
  redacted_item_count: 2,
  redaction_decisions: [
    { id: "redact-1", category: "secrets", path_or_ref: ".env", reason: "secret file", decision: "exclude" },
    {
      id: "redact-2",
      category: "provider-cache",
      path_or_ref: ".hydralab/cache/provider/openai/payload.json",
      reason: "provider cache",
      decision: "exclude",
    },
  ],
};

describe("reproducibility controller", () => {
  test("build action is disabled until a run is selected", () => {
    expect(canBuildBundle([], [])).toBe(false);
    expect(canBuildBundle(runs, [])).toBe(false);
    expect(canBuildBundle(runs, [runs[0].id])).toBe(true);
  });

  test("review surface exposes categories and redacted item count", () => {
    expect(includedCategoryLabels(preview)).toEqual(["Sources", "Artifacts", "Ledger"]);
    expect(reviewRedactionCount(preview)).toBe(2);
  });

  test("bundle request is explicit and stable", () => {
    expect(buildBundleRequest("default", [runs[0].id], "approval-1")).toEqual({
      project_id: "default",
      run_ids: ["run-2026-06-20-attention-replication"],
      approval_id: "approval-1",
    });
  });
});
