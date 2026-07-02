import type { HydraApiError } from "../../lib/api";
import type { DocxEditOperation, DocxEditPlanResponse } from "../../lib/api";

// Branch 02-08: DOCX OpenXML assisted-edit review surface (HL-WRITE-35,
// HL-QUAL-30). Pure controller logic so the panel stays declarative and the
// gating rules (only-approved-applies, four UI states, untrusted labelling)
// are unit-tested independently of React.

export type DocxPlanUiState = "empty" | "loading" | "failure" | "permission-denied" | "ready";

export function docxPlanUiState(args: {
  loading: boolean;
  error: Error | HydraApiError | null;
  plan: DocxEditPlanResponse | null;
}): DocxPlanUiState {
  if (args.loading) return "loading";
  if (args.error) {
    const apiError = args.error as HydraApiError;
    if (apiError.kind === "permission-denied" || apiError.kind === "consent-required") return "permission-denied";
    return "failure";
  }
  if (!args.plan || args.plan.operations.length === 0) return "empty";
  return "ready";
}

// HL-WRITE-35: no operation with review_status !== "approved" may be applied.
export function approvedOperations(operations: DocxEditOperation[]): DocxEditOperation[] {
  return operations.filter((op) => op.review_status === "approved");
}

export function canApplyPlan(operations: DocxEditOperation[]): boolean {
  return approvedOperations(operations).length > 0;
}

export type ReviewProgress = { approved: number; rejected: number; pending: number; total: number };

export function summarizeReviewProgress(operations: DocxEditOperation[]): ReviewProgress {
  return operations.reduce<ReviewProgress>(
    (acc, op) => {
      acc.total += 1;
      if (op.review_status === "approved") acc.approved += 1;
      else if (op.review_status === "rejected") acc.rejected += 1;
      else acc.pending += 1;
      return acc;
    },
    { approved: 0, rejected: 0, pending: 0, total: 0 },
  );
}

export function operationLocationLabel(op: DocxEditOperation): string {
  return op.location_label || op.target_locator || "Unknown location";
}

export function isUntrusted(op: DocxEditOperation): boolean {
  return op.trust_level === "untrusted-external";
}

export function riskBadgeClass(risk: string): string {
  if (risk === "high") return "risk-badge risk-high";
  if (risk === "medium") return "risk-badge risk-medium";
  return "risk-badge risk-low";
}

// A human one-line diff summary for an operation (before → after).
export function operationDiffSummary(op: DocxEditOperation): string {
  const before = op.before_summary || "(empty)";
  const after = op.after_summary || "(empty)";
  return `${before} → ${after}`;
}
