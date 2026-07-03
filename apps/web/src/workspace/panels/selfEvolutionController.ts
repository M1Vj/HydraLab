import { api, type ApiClient } from "../../lib/api";

/** A single typed self-evolution change (branch 03-05, HL-ASSIST-30..35). */
export type SelfEvolutionCategory = "skill" | "prompt" | "setting" | "app_code";
export type SelfEvolutionRiskClass = "auto_eligible" | "review_required";
export type SelfEvolutionTrustLevel = "user" | "untrusted-external";
export type SelfEvolutionStatus = "proposed" | "approved" | "applied" | "rolled_back" | "denied";

export type SelfEvolutionChange = {
  id: string;
  change_id: string;
  changeset_id: string;
  project_id: string;
  run_id?: string | null;
  category: SelfEvolutionCategory | string;
  target_path: string;
  unified_diff: string;
  test_plan: string[];
  risk_class: SelfEvolutionRiskClass | string;
  risk_reason: string;
  trust_level: SelfEvolutionTrustLevel | string;
  origin: string;
  status: SelfEvolutionStatus | string;
  checkpoint_ref?: string | null;
  verification_result: "pass" | "fail" | "" | string;
  review_inbox: boolean;
  created_at: number;
  updated_at: number;
};

export type SelfEvolutionAuditEntry = {
  id: string;
  action: string;
  actor: string;
  risk_level: string;
  target: string;
  approval_state: string;
  created_at: number;
};

export type Tone = "ok" | "warn" | "danger" | "muted";
export type Badge = { label: string; tone: Tone };

/**
 * A change may be approved (which triggers checkpoint → apply → verify) only
 * when it is still proposed, carries a non-empty test plan, is trusted, and is
 * not a protected-target (review_required) diff. Protected/untrusted diffs route
 * to the Review Inbox and never auto-apply (HL-ASSIST-31/32, HL-TRUST-20/21).
 */
export function canApprove(change: SelfEvolutionChange): boolean {
  return (
    change.status === "proposed" &&
    change.test_plan.length > 0 &&
    change.risk_class !== "review_required" &&
    change.trust_level !== "untrusted-external"
  );
}

export function approveDisabledReason(change: SelfEvolutionChange): string | null {
  if (change.status !== "proposed") return `Change is ${change.status}.`;
  if (change.test_plan.length === 0) return "A test plan is required before this change can be applied.";
  if (change.trust_level === "untrusted-external")
    return "Untrusted-external proposals route to the Review Inbox and cannot be auto-applied.";
  if (change.risk_class === "review_required")
    return "Protected-field changes route to the Review Inbox and cannot be auto-applied.";
  return null;
}

export function riskBadge(change: SelfEvolutionChange): Badge {
  return change.risk_class === "review_required"
    ? { label: "review required", tone: "danger" }
    : { label: "auto-eligible", tone: "ok" };
}

export function trustBadge(change: SelfEvolutionChange): Badge {
  return change.trust_level === "untrusted-external"
    ? { label: "untrusted-external", tone: "danger" }
    : { label: "user-trusted", tone: "muted" };
}

export function statusBadge(change: SelfEvolutionChange): Badge {
  switch (change.status) {
    case "applied":
      return { label: "applied", tone: "ok" };
    case "rolled_back":
      return { label: "rolled back", tone: "warn" };
    case "denied":
      return { label: "denied", tone: "muted" };
    case "approved":
      return { label: "approved", tone: "muted" };
    default:
      return { label: "proposed", tone: "muted" };
  }
}

export function listSelfEvolutionChanges(
  projectId = "default",
  client: ApiClient = api,
): Promise<{ changes: SelfEvolutionChange[] }> {
  return client.get<{ changes: SelfEvolutionChange[] }>(
    `/api/self-evolution/changes?project_id=${encodeURIComponent(projectId)}`,
  );
}

export function approveSelfEvolutionChange(
  changeId: string,
  client: ApiClient = api,
): Promise<{ change: SelfEvolutionChange }> {
  return client.post<{ change: SelfEvolutionChange }>(
    `/api/self-evolution/changes/${encodeURIComponent(changeId)}/approve`,
    { actor: "user" },
  );
}

export function denySelfEvolutionChange(
  changeId: string,
  client: ApiClient = api,
): Promise<{ change: SelfEvolutionChange }> {
  return client.post<{ change: SelfEvolutionChange }>(
    `/api/self-evolution/changes/${encodeURIComponent(changeId)}/deny`,
    { actor: "user" },
  );
}

export function fetchSelfEvolutionAudit(
  projectId = "default",
  client: ApiClient = api,
): Promise<{ entries: SelfEvolutionAuditEntry[] }> {
  return client.get<{ entries: SelfEvolutionAuditEntry[] }>(
    `/api/self-evolution/audit?project_id=${encodeURIComponent(projectId)}`,
  );
}
