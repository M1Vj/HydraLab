import {
  api,
  type AgentTraceStep,
  type ApiClient,
  type OrchestratorRunResponse,
  type OrchestratorStage,
} from "../../lib/api";

export const CANONICAL_STAGE_IDS = [
  "generate",
  "review",
  "compare",
  "evolve",
  "validate",
  "cache",
  "loop_control",
] as const;

export type StageId = (typeof CANONICAL_STAGE_IDS)[number];
export type StageToggles = Record<StageId, boolean>;

export function defaultStageToggles(): StageToggles {
  return Object.fromEntries(CANONICAL_STAGE_IDS.map((id) => [id, true])) as StageToggles;
}

export function normalizeStageToggles(partial: Partial<Record<string, boolean>> = {}): StageToggles {
  const defaults = defaultStageToggles();
  for (const id of CANONICAL_STAGE_IDS) {
    if (Object.prototype.hasOwnProperty.call(partial, id)) defaults[id] = Boolean(partial[id]);
  }
  return defaults;
}

export function toggleStage(current: Partial<Record<string, boolean>>, stage: StageId, enabled: boolean): StageToggles {
  return normalizeStageToggles({ ...current, [stage]: enabled });
}

export function buildStartRunPayload(projectId: string, toggles: Partial<Record<string, boolean>>) {
  return {
    project_id: projectId,
    enabled_stages: normalizeStageToggles(toggles),
  };
}

export function fetchOrchestratorStages(client: ApiClient = api): Promise<OrchestratorStage[]> {
  return client.get<{ stages: OrchestratorStage[] }>("/api/orchestrator/stages").then((payload) => payload.stages);
}

export function startOrchestratorRun(
  projectId: string,
  toggles: Partial<Record<string, boolean>>,
  client: ApiClient = api,
): Promise<OrchestratorRunResponse> {
  return client.post<OrchestratorRunResponse>("/api/orchestrator/runs", buildStartRunPayload(projectId, toggles));
}

export function fetchOrchestratorRun(runId: string, client: ApiClient = api): Promise<OrchestratorRunResponse> {
  return client.get<OrchestratorRunResponse>(`/api/agent/runs/${encodeURIComponent(runId)}`);
}

export function summarizeRunState(status: string, state?: string): string {
  if (state === "budget_blocked" || status === "blocked") return "Budget blocked";
  if (state === "awaiting_approval") return "Awaiting approval";
  if (state === "permission-denied" || status === "permission-denied") return "Permission denied";
  if (status === "failed") return "Failed";
  if (status === "completed") return "Completed";
  if (status === "running") return "Running";
  return status.replace(/_/g, " ");
}

export function stageStatus(steps: AgentTraceStep[], stage: StageId): string {
  return steps.find((step) => step.kind === `stage.${stage}`)?.status ?? "pending";
}
