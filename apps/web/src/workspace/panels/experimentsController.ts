import { api, type ApiClient } from "../../lib/api";

// Mirrors the backend gated compute subsystem (branch 03-03, HL-SAFE-10..19).
export type ComputeBackend = {
  id: string;
  kind: "local_sandbox" | "cloud" | string;
  display_name: string;
  enabled: boolean;
  capabilities: Record<string, unknown>;
  default_limits: Record<string, number>;
};

export type ExperimentRunStatus =
  | "pending"
  | "awaiting_approval"
  | "running"
  | "paused"
  | "succeeded"
  | "failed"
  | "cancelled"
  | string; // killed:<reason>

export type ExperimentRun = {
  id: string;
  project_id: string;
  backend_id: string | null;
  label: string;
  status: ExperimentRunStatus;
  reason: string;
  config: Record<string, unknown>;
  checkpoint_ref: string | null;
  metrics: Record<string, number>;
  enforcement: string;
  exit_code: number | null;
  approval_id: string | null;
  review_item_id: string | null;
  created_at: number;
  ended_at: number | null;
};

export type ExecutionSetting = {
  project_id: string;
  execution_enabled: boolean;
  cloud_budget_usd: number | null;
  cloud_spend_approved: boolean;
};

export type ExperimentRunLogRow = {
  id: string;
  run_id: string;
  stream: "stdout" | "stderr" | "metric" | string;
  seq: number;
  content: string;
  truncated: boolean;
  created_at: number;
};

export type PanelState = "loading" | "permission-denied" | "empty" | "failure" | "ready";

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

export function isTerminal(status: ExperimentRunStatus): boolean {
  return TERMINAL.has(status) || status.startsWith("killed:");
}

export function statusLabel(status: ExperimentRunStatus): string {
  if (status.startsWith("killed:")) return `Killed (${status.slice("killed:".length)})`;
  switch (status) {
    case "awaiting_approval":
      return "Awaiting approval";
    case "running":
      return "Running";
    case "paused":
      return "Paused";
    case "succeeded":
      return "Succeeded";
    case "failed":
      return "Failed";
    case "cancelled":
      return "Cancelled";
    default:
      return status.replace(/_/g, " ");
  }
}

/**
 * Derive the panel state (DEC-12: every capability defines empty/loading/
 * failure/permission states). Execution-disabled always resolves to the
 * permission-denied "Enable execution" surface, never to run controls.
 */
export function derivePanelState(input: {
  loading: boolean;
  error: unknown;
  executionEnabled: boolean;
  runCount: number;
}): PanelState {
  if (input.loading) return "loading";
  if (input.error) return "failure";
  if (!input.executionEnabled) return "permission-denied";
  if (input.runCount === 0) return "empty";
  return "ready";
}

/** Run controls are inert until execution is enabled for the project (HL-SAFE-17). */
export function runControlsEnabled(setting: ExecutionSetting | null): boolean {
  return Boolean(setting?.execution_enabled);
}

export function canApprove(run: ExperimentRun): boolean {
  return run.status === "awaiting_approval" && Boolean(run.approval_id) && !run.review_item_id;
}

export function canStart(run: ExperimentRun, setting: ExecutionSetting | null): boolean {
  return runControlsEnabled(setting) && run.status === "awaiting_approval" && !run.review_item_id;
}

export function canPauseOrCancel(run: ExperimentRun): boolean {
  return run.status === "running" || run.status === "paused";
}

export function canRollback(run: ExperimentRun): boolean {
  return Boolean(run.checkpoint_ref) && isTerminal(run.status);
}

export function selectableBackends(backends: ComputeBackend[]): ComputeBackend[] {
  return backends.filter((backend) => backend.enabled);
}

export function buildCreateRunPayload(input: {
  projectId: string;
  backendId: string;
  label: string;
  argv: string[];
  trustOrigin?: string;
}) {
  return {
    project_id: input.projectId,
    backend_id: input.backendId,
    label: input.label,
    config: { argv: input.argv },
    trust_origin: input.trustOrigin ?? "user",
    justification_trust: input.trustOrigin ?? "user",
  };
}

// --- API surface -----------------------------------------------------------
export function fetchExecutionSetting(projectId: string, client: ApiClient = api): Promise<ExecutionSetting> {
  return client.get<ExecutionSetting>(`/api/experiments/execution?project_id=${encodeURIComponent(projectId)}`);
}

export function enableExecution(projectId: string, client: ApiClient = api): Promise<{ execution_enabled: boolean }> {
  return client.post("/api/experiments/execution/enable", { project_id: projectId, enabled: true });
}

export function fetchBackends(client: ApiClient = api): Promise<ComputeBackend[]> {
  return client.get<{ backends: ComputeBackend[] }>("/api/compute/backends").then((payload) => payload.backends);
}

export function fetchRuns(projectId: string, client: ApiClient = api): Promise<ExperimentRun[]> {
  return client
    .get<{ runs: ExperimentRun[] }>(`/api/experiments/runs?project_id=${encodeURIComponent(projectId)}`)
    .then((payload) => payload.runs);
}

export function createRun(
  payload: ReturnType<typeof buildCreateRunPayload>,
  client: ApiClient = api,
): Promise<{ run: ExperimentRun; approval_id: string | null; review_item_id: string | null }> {
  return client.post("/api/experiments/runs", payload);
}

export function approveRun(runId: string, decision: "approve" | "reject" = "approve", client: ApiClient = api) {
  return client.post<{ run: ExperimentRun }>(`/api/experiments/runs/${encodeURIComponent(runId)}/approve`, { decision });
}

export function startRun(runId: string, client: ApiClient = api) {
  return client.post<{ run: ExperimentRun }>(`/api/experiments/runs/${encodeURIComponent(runId)}/start`, {});
}

export function pauseRun(runId: string, client: ApiClient = api) {
  return client.post<{ run: ExperimentRun }>(`/api/experiments/runs/${encodeURIComponent(runId)}/pause`, {});
}

export function cancelRun(runId: string, client: ApiClient = api) {
  return client.post<{ run: ExperimentRun }>(`/api/experiments/runs/${encodeURIComponent(runId)}/cancel`, {});
}

export function rollbackRun(runId: string, client: ApiClient = api) {
  return client.post<{ run: ExperimentRun }>(`/api/experiments/runs/${encodeURIComponent(runId)}/rollback`, {});
}

export function fetchRunLogs(runId: string, client: ApiClient = api): Promise<ExperimentRunLogRow[]> {
  return client
    .get<{ logs: ExperimentRunLogRow[] }>(`/api/experiments/runs/${encodeURIComponent(runId)}/logs`)
    .then((payload) => payload.logs);
}
