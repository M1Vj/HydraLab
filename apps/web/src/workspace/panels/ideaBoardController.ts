import {
  api,
  type AgentTraceStep,
  type ApiClient,
  type HydraApiError,
  type IdeaCandidate,
  type IdeaPromotionResponse,
  type IdeaRunResponse,
} from "../../lib/api";

// Slash commands that resolve to the built-in idea recipe (HL-ASSIST-01).
export const IDEA_SLASH_COMMANDS = ["/generate-hypotheses", "/rank-ideas"] as const;

// Only the four stages the recipe exposes as toggles (HL-ASSIST-10). NO
// loop-count / population-size / stop-condition control exists.
export const IDEA_STAGE_IDS = ["generate", "review", "compare", "evolve"] as const;
export type IdeaStageId = (typeof IDEA_STAGE_IDS)[number];
export type IdeaStageToggles = Record<IdeaStageId, boolean>;

export type PromotableTarget = "task" | "note" | "related_work";

export type IdeaBoardStateKind = "empty" | "loading" | "failure" | "permission-denied" | "ready";

export type IdeaBoardState = {
  kind: IdeaBoardStateKind;
  message: string;
  completedStages: IdeaStageId[];
  candidates: IdeaCandidate[];
};

// The four required UI-state messages (HL-ASSIST-13).
export const IDEA_STATE_MESSAGES = {
  empty: "No candidates yet — run /generate-hypotheses",
  loading: "Running the idea recipe — streaming stage progress",
  failure: "A stage failed — completed stages are preserved below. Retry when ready.",
  permissionDenied: "Provider access is blocked (offline-only or consent gate G3). No request was sent.",
} as const;

export function defaultIdeaToggles(): IdeaStageToggles {
  // Generate + Review + Compare on by default; Evolve is an opt-in single pass.
  return { generate: true, review: true, compare: true, evolve: false };
}

export function normalizeIdeaToggles(partial: Partial<Record<string, boolean>> = {}): IdeaStageToggles {
  const defaults = defaultIdeaToggles();
  for (const id of IDEA_STAGE_IDS) {
    if (Object.prototype.hasOwnProperty.call(partial, id)) defaults[id] = Boolean(partial[id]);
  }
  return defaults;
}

export function toggleIdeaStage(
  current: Partial<Record<string, boolean>>,
  stage: IdeaStageId,
  enabled: boolean,
): IdeaStageToggles {
  return normalizeIdeaToggles({ ...current, [stage]: enabled });
}

export type IdeaRunInputFields = {
  topic: string;
  source_scope?: string;
  constraints?: string;
  novelty_target?: string;
};

export function buildIdeaRunPayload(
  projectId: string,
  input: IdeaRunInputFields,
  toggles: Partial<Record<string, boolean>>,
) {
  return {
    project_id: projectId,
    topic: input.topic,
    source_scope: input.source_scope ?? "",
    constraints: input.constraints ?? "",
    novelty_target: input.novelty_target ?? "medium",
    enabled_stages: normalizeIdeaToggles(toggles),
  };
}

export function startIdeaRun(
  projectId: string,
  input: IdeaRunInputFields,
  toggles: Partial<Record<string, boolean>>,
  client: ApiClient = api,
): Promise<IdeaRunResponse> {
  return client.post<IdeaRunResponse>("/api/recipes/idea/runs", buildIdeaRunPayload(projectId, input, toggles));
}

export function fetchIdeaRun(runId: string, client: ApiClient = api): Promise<IdeaRunResponse> {
  return client.get<IdeaRunResponse>(`/api/recipes/idea/runs/${encodeURIComponent(runId)}`);
}

export function promoteCandidate(
  projectId: string,
  candidateId: string,
  targetKind: PromotableTarget,
  client: ApiClient = api,
): Promise<IdeaPromotionResponse> {
  return client.post<IdeaPromotionResponse>("/api/recipes/idea/promote", {
    project_id: projectId,
    candidate_id: candidateId,
    target_kind: targetKind,
  });
}

export function resolveIdeaPromotion(
  reviewItemId: string,
  decision: "approve" | "reject",
  client: ApiClient = api,
): Promise<IdeaPromotionResponse> {
  return client.post<IdeaPromotionResponse>(
    `/api/recipes/idea/promotions/${encodeURIComponent(reviewItemId)}/resolve`,
    { decision },
  );
}

// The completed stage prefix (in canonical order) from the run trace. A
// mid-stream failure preserves this prefix (HL-ASSIST-13).
export function completedStagePrefix(steps: AgentTraceStep[]): IdeaStageId[] {
  const done = new Set(
    steps
      .filter((step) => step.status === "completed" && step.kind.startsWith("stage."))
      .map((step) => step.kind.replace("stage.", "")),
  );
  return IDEA_STAGE_IDS.filter((id) => done.has(id));
}

export function ideaStageStatus(steps: AgentTraceStep[], stage: IdeaStageId): string {
  return steps.find((step) => step.kind === `stage.${stage}`)?.status ?? "pending";
}

export function isPermissionDenied(run: IdeaRunResponse | null): boolean {
  if (!run) return false;
  const state = run.run.state ?? run.run.status;
  if (state === "permission-denied") return true;
  if (run.run.status === "blocked") {
    return run.trace.steps.some((step) => step.kind === "consent.offline_blocked");
  }
  return false;
}

export function deriveIdeaBoardState(args: {
  loading: boolean;
  error: (Error | HydraApiError) | null;
  run: IdeaRunResponse | null;
}): IdeaBoardState {
  const { loading, error, run } = args;
  const completedStages = run ? completedStagePrefix(run.trace.steps) : [];
  const candidates = run?.candidates ?? [];

  if (loading) {
    return { kind: "loading", message: IDEA_STATE_MESSAGES.loading, completedStages, candidates };
  }
  if (error) {
    const apiError = error as HydraApiError;
    if (apiError.kind === "permission-denied" || apiError.kind === "consent-required") {
      return { kind: "permission-denied", message: IDEA_STATE_MESSAGES.permissionDenied, completedStages, candidates };
    }
    return { kind: "failure", message: error.message || IDEA_STATE_MESSAGES.failure, completedStages, candidates };
  }
  if (run) {
    if (isPermissionDenied(run)) {
      return { kind: "permission-denied", message: IDEA_STATE_MESSAGES.permissionDenied, completedStages, candidates };
    }
    if (run.run.status === "failed") {
      return { kind: "failure", message: IDEA_STATE_MESSAGES.failure, completedStages, candidates };
    }
    if (candidates.length === 0) {
      return { kind: "empty", message: IDEA_STATE_MESSAGES.empty, completedStages, candidates };
    }
    return { kind: "ready", message: "", completedStages, candidates };
  }
  return { kind: "empty", message: IDEA_STATE_MESSAGES.empty, completedStages: [], candidates: [] };
}

// Candidates in ranked order (unranked candidates keep insertion order and carry
// no score column, HL-ASSIST-08).
export function rankedCandidates(candidates: IdeaCandidate[]): IdeaCandidate[] {
  return [...candidates].sort((a, b) => {
    const ra = a.rank ?? Number.MAX_SAFE_INTEGER;
    const rb = b.rank ?? Number.MAX_SAFE_INTEGER;
    if (ra !== rb) return ra - rb;
    return a.id.localeCompare(b.id);
  });
}

export function hasRubricScores(candidates: IdeaCandidate[]): boolean {
  return candidates.some((candidate) => candidate.rubric_results.length > 0);
}
