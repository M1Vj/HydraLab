import { describe, expect, test } from "bun:test";
import { HydraApiError } from "../../lib/api";
import type { DocxEditOperation, DocxEditPlanResponse } from "../../lib/api";
import {
  approvedOperations,
  canApplyPlan,
  docxPlanUiState,
  isUntrusted,
  operationDiffSummary,
  operationLocationLabel,
  riskBadgeClass,
  summarizeReviewProgress,
} from "./docxEditPlan";

function op(overrides: Partial<DocxEditOperation> = {}): DocxEditOperation {
  return {
    id: "op-1",
    plan_id: "plan-1",
    op_type: "replace_text",
    target_locator: "body/p/0",
    location_label: "Body ¶1",
    before_summary: "Old Title",
    after_summary: "New Title",
    payload: { text: "New Title" },
    risk_label: "low",
    review_status: "pending",
    validation_status: "unvalidated",
    applied: false,
    trust_level: "trusted",
    ...overrides,
  };
}

function plan(operations: DocxEditOperation[]): DocxEditPlanResponse {
  return {
    plan: {
      id: "plan-1",
      manuscript: "survey",
      target_relpath: "draft.docx",
      status: "draft",
      mode: "passive",
      trust_level: "trusted",
    },
    operations,
  };
}

describe("DOCX edit-plan controller", () => {
  test("four UI states are reachable (HL-QUAL-30)", () => {
    expect(docxPlanUiState({ loading: true, error: null, plan: null })).toBe("loading");
    expect(docxPlanUiState({ loading: false, error: null, plan: null })).toBe("empty");
    expect(docxPlanUiState({ loading: false, error: null, plan: plan([]) })).toBe("empty");
    expect(docxPlanUiState({ loading: false, error: new Error("boom"), plan: null })).toBe("failure");
    const denied = new HydraApiError({ kind: "permission-denied", message: "G1 consent not granted" });
    expect(docxPlanUiState({ loading: false, error: denied, plan: null })).toBe("permission-denied");
    expect(docxPlanUiState({ loading: false, error: null, plan: plan([op()]) })).toBe("ready");
  });

  test("only approved operations are applicable (HL-WRITE-35)", () => {
    const ops = [
      op({ id: "a", review_status: "approved" }),
      op({ id: "b", review_status: "approved" }),
      op({ id: "c", review_status: "pending" }),
    ];
    expect(approvedOperations(ops).map((o) => o.id)).toEqual(["a", "b"]);
    expect(canApplyPlan(ops)).toBe(true);
    expect(canApplyPlan([op({ review_status: "pending" }), op({ review_status: "rejected" })])).toBe(false);
  });

  test("review progress is summarized for the reviewer", () => {
    const progress = summarizeReviewProgress([
      op({ review_status: "approved" }),
      op({ review_status: "rejected" }),
      op({ review_status: "pending" }),
      op({ review_status: "pending" }),
    ]);
    expect(progress).toEqual({ approved: 1, rejected: 1, pending: 2, total: 4 });
  });

  test("location label falls back to the raw locator", () => {
    expect(operationLocationLabel(op({ location_label: "Table 1, row 3, cell 2" }))).toBe("Table 1, row 3, cell 2");
    expect(operationLocationLabel(op({ location_label: "", target_locator: "body/tbl/0/row/2/cell/1" }))).toBe(
      "body/tbl/0/row/2/cell/1",
    );
  });

  test("untrusted-external operations are flagged (HL-TRUST-30)", () => {
    expect(isUntrusted(op({ trust_level: "untrusted-external" }))).toBe(true);
    expect(isUntrusted(op({ trust_level: "trusted" }))).toBe(false);
  });

  test("risk badge class maps risk level", () => {
    expect(riskBadgeClass("high")).toContain("risk-high");
    expect(riskBadgeClass("medium")).toContain("risk-medium");
    expect(riskBadgeClass("low")).toContain("risk-low");
  });

  test("diff summary renders before → after", () => {
    expect(operationDiffSummary(op({ before_summary: "A", after_summary: "B" }))).toBe("A → B");
    expect(operationDiffSummary(op({ before_summary: "", after_summary: "" }))).toBe("(empty) → (empty)");
  });
});
