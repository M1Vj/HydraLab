import {
  api,
  type AutonomyAuditEntry,
  type AutonomyPendingAction,
  type AutonomyPolicy,
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
export const BUILTIN_RECIPE_IDS = ["paper-critique", "related-work"] as const;

export type StageId = (typeof CANONICAL_STAGE_IDS)[number];
export type BuiltinRecipeId = (typeof BUILTIN_RECIPE_IDS)[number];
export type StageToggles = Record<StageId, boolean>;
export type RankingMethod = "pairwise" | "tournament" | "elo" | "rubric";
export type EvolutionMethod = "none" | "refine" | "merge" | "mutate" | "crossover";
export type ValidationRule = "typecheck" | "lint" | "test" | "build";
export type StopCondition =
  | "max_loop_iterations"
  | "token_budget"
  | "wall_clock_budget"
  | "cost_budget"
  | "quality_plateau"
  | "user_stop";
export type BudgetPolicy = {
  tokens: number;
  wall_clock_seconds: number;
  cost_usd: number | null;
};
export type AdvancedRunConfig = {
  candidate_count: number;
  population_size: number;
  compare_enabled: boolean;
  ranking_method: RankingMethod;
  review_depth: number;
  evolution_method: EvolutionMethod;
  validation_rules: ValidationRule[];
  max_loop_iterations: number;
  stop_conditions: StopCondition[];
  budget_policy: BudgetPolicy;
  checkpoint_frequency: number;
};
export type AdvancedValidationState = "empty" | "loading" | "failure" | "permission-denied" | "ready";
export type AdvancedValidationError = { field: string; allowed: string; received: unknown };
export type AdvancedValidationResult = {
  state: AdvancedValidationState;
  error: AdvancedValidationError | null;
};
export type LiteratureDepth = "quick" | "standard" | "deep";
export type LiteratureReviewFormInput = {
  question: string;
  sourceScope: Record<string, unknown>;
  depth: LiteratureDepth;
  semanticSearch?: boolean;
};

export type AutonomyPolicyPayload = AutonomyPolicy & { project_id: string };

export type RecipeDescriptor = {
  id: BuiltinRecipeId | string;
  name: string;
  stages: string[];
  input_schema?: Record<string, unknown>;
  approval_gates?: string[];
  output_artifact_type?: string;
};

export type RecipeLaunchInputs = {
  recipe_id: BuiltinRecipeId | string;
  draft_or_source: { title: string; text: string };
  target_venue_style: string;
  source_scope: string[];
};

export function defaultStageToggles(): StageToggles {
  return Object.fromEntries(CANONICAL_STAGE_IDS.map((id) => [id, true])) as StageToggles;
}

export const ADVANCED_RANKING_METHODS = ["pairwise", "tournament", "elo", "rubric"] as const;
export const ADVANCED_EVOLUTION_METHODS = ["none", "refine", "merge", "mutate", "crossover"] as const;
export const ADVANCED_VALIDATION_RULES = ["typecheck", "lint", "test", "build"] as const;
export const ADVANCED_STOP_CONDITIONS = [
  "max_loop_iterations",
  "token_budget",
  "wall_clock_budget",
  "cost_budget",
  "quality_plateau",
  "user_stop",
] as const;

export const ADVANCED_RUN_PRESETS: Record<string, AdvancedRunConfig> = {
  fast: {
    candidate_count: 2,
    population_size: 4,
    compare_enabled: true,
    ranking_method: "pairwise",
    review_depth: 1,
    evolution_method: "none",
    validation_rules: ["typecheck", "test"],
    max_loop_iterations: 1,
    stop_conditions: ["max_loop_iterations", "token_budget", "wall_clock_budget"],
    budget_policy: { tokens: 30000, wall_clock_seconds: 60, cost_usd: null },
    checkpoint_frequency: 1,
  },
  balanced: {
    candidate_count: 3,
    population_size: 12,
    compare_enabled: true,
    ranking_method: "pairwise",
    review_depth: 2,
    evolution_method: "refine",
    validation_rules: ["typecheck", "lint", "test", "build"],
    max_loop_iterations: 1,
    stop_conditions: ["max_loop_iterations", "token_budget", "wall_clock_budget"],
    budget_policy: { tokens: 60000, wall_clock_seconds: 120, cost_usd: null },
    checkpoint_frequency: 1,
  },
  deep: {
    candidate_count: 6,
    population_size: 24,
    compare_enabled: true,
    ranking_method: "tournament",
    review_depth: 4,
    evolution_method: "merge",
    validation_rules: ["typecheck", "lint", "test", "build"],
    max_loop_iterations: 3,
    stop_conditions: ["max_loop_iterations", "token_budget", "wall_clock_budget", "quality_plateau"],
    budget_policy: { tokens: 60000, wall_clock_seconds: 120, cost_usd: null },
    checkpoint_frequency: 1,
  },
  exploratory: {
    candidate_count: 8,
    population_size: 40,
    compare_enabled: true,
    ranking_method: "elo",
    review_depth: 3,
    evolution_method: "mutate",
    validation_rules: ["typecheck", "test"],
    max_loop_iterations: 4,
    stop_conditions: ["max_loop_iterations", "token_budget", "wall_clock_budget", "quality_plateau"],
    budget_policy: { tokens: 80000, wall_clock_seconds: 180, cost_usd: null },
    checkpoint_frequency: 2,
  },
  strict_evidence: {
    candidate_count: 4,
    population_size: 16,
    compare_enabled: true,
    ranking_method: "rubric",
    review_depth: 5,
    evolution_method: "refine",
    validation_rules: ["typecheck", "lint", "test", "build"],
    max_loop_iterations: 2,
    stop_conditions: ["max_loop_iterations", "token_budget", "wall_clock_budget"],
    budget_policy: { tokens: 60000, wall_clock_seconds: 120, cost_usd: null },
    checkpoint_frequency: 1,
  },
};

export function buildAdvancedRunConfig(
  presetId = "balanced",
  overrides: Partial<AdvancedRunConfig> = {},
): AdvancedRunConfig {
  const preset = ADVANCED_RUN_PRESETS[presetId] ?? ADVANCED_RUN_PRESETS.balanced;
  return {
    ...preset,
    ...overrides,
    validation_rules: [...(overrides.validation_rules ?? preset.validation_rules)],
    stop_conditions: [...(overrides.stop_conditions ?? preset.stop_conditions)],
    budget_policy: { ...preset.budget_policy, ...(overrides.budget_policy ?? {}) },
  };
}

export function validateAdvancedRunConfig(
  config: AdvancedRunConfig,
  options: { autopilotEnabled?: boolean } = {},
): AdvancedValidationResult {
  if (options.autopilotEnabled === false) return { state: "permission-denied", error: null };
  const checks: Array<[keyof AdvancedRunConfig | string, boolean, string, unknown]> = [
    ["candidate_count", inRange(config.candidate_count, 1, 20), "1..20", config.candidate_count],
    ["population_size", inRange(config.population_size, 1, 100), "1..100", config.population_size],
    ["ranking_method", includes(ADVANCED_RANKING_METHODS, config.ranking_method), "elo, pairwise, rubric, tournament", config.ranking_method],
    ["review_depth", inRange(config.review_depth, 1, 5), "1..5", config.review_depth],
    ["evolution_method", includes(ADVANCED_EVOLUTION_METHODS, config.evolution_method), "crossover, merge, mutate, none, refine", config.evolution_method],
    ["validation_rules", config.validation_rules.length > 0 && config.validation_rules.every((rule) => includes(ADVANCED_VALIDATION_RULES, rule)), "build, lint, test, typecheck", config.validation_rules],
    ["max_loop_iterations", inRange(config.max_loop_iterations, 1, 100), "1..100", config.max_loop_iterations],
    ["stop_conditions", config.stop_conditions.length > 0 && config.stop_conditions.every((rule) => includes(ADVANCED_STOP_CONDITIONS, rule)), "cost_budget, max_loop_iterations, quality_plateau, token_budget, user_stop, wall_clock_budget", config.stop_conditions],
    ["budget_policy.tokens", inRange(config.budget_policy.tokens, 1, 200000), "1..200000", config.budget_policy.tokens],
    ["budget_policy.wall_clock_seconds", inRange(config.budget_policy.wall_clock_seconds, 1, 3600), "1..3600", config.budget_policy.wall_clock_seconds],
    ["checkpoint_frequency", inRange(config.checkpoint_frequency, 1, 25), "1..25", config.checkpoint_frequency],
  ];
  const failed = checks.find(([, valid]) => !valid);
  if (failed) return { state: "failure", error: { field: String(failed[0]), allowed: failed[2], received: failed[3] } };
  return { state: "ready", error: null };
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

export function buildStartRunPayload(
  projectId: string,
  toggles: Partial<Record<string, boolean>>,
  recipe?: RecipeLaunchInputs,
) {
  return {
    project_id: projectId,
    enabled_stages: normalizeStageToggles(toggles),
    ...(recipe
      ? {
          recipe_id: recipe.recipe_id,
          recipe_inputs: {
            draft_or_source: recipe.draft_or_source,
            target_venue_style: recipe.target_venue_style,
            source_scope: recipe.source_scope,
          },
        }
      : {}),
  };
}

export function buildStartAutopilotPayload(
  projectId: string,
  toggles: Partial<Record<string, boolean>>,
  advancedConfig?: AdvancedRunConfig,
  presetId = "balanced",
  trustOrigin = "user",
) {
  return {
    project_id: projectId,
    enabled_stages: normalizeStageToggles(toggles),
    ...(advancedConfig
      ? {
          advanced_preset_id: presetId,
          advanced_config: advancedConfig,
          advanced_config_trust_origin: trustOrigin,
        }
      : {}),
  };
}

export function buildLiteratureReviewPayload(projectId: string, input: LiteratureReviewFormInput) {
  return {
    project_id: projectId,
    question: input.question.trim(),
    source_scope: input.sourceScope,
    depth: input.depth,
    semantic_search: Boolean(input.semanticSearch),
  };
}

export function fetchOrchestratorStages(client: ApiClient = api): Promise<OrchestratorStage[]> {
  return client.get<{ stages: OrchestratorStage[] }>("/api/orchestrator/stages").then((payload) => payload.stages);
}

export function fetchRecipes(client: ApiClient = api): Promise<RecipeDescriptor[]> {
  return client.get<{ recipes: RecipeDescriptor[] }>("/api/orchestrator/recipes").then((payload) => payload.recipes);
}

export function fetchAutonomyPolicy(projectId: string, client: ApiClient = api): Promise<AutonomyPolicy> {
  return client
    .get<{ policy: AutonomyPolicy }>(`/api/autonomy/policy?project_id=${encodeURIComponent(projectId)}`)
    .then((payload) => payload.policy);
}

export function saveAutonomyPolicy(payload: AutonomyPolicyPayload, client: ApiClient = api): Promise<AutonomyPolicy> {
  return client.post<{ policy: AutonomyPolicy }>("/api/autonomy/policy", payload).then((response) => response.policy);
}

export function startAutopilotRun(
  projectId: string,
  toggles: Partial<Record<string, boolean>>,
  client: ApiClient = api,
  advancedConfig?: AdvancedRunConfig,
  presetId = "balanced",
): Promise<OrchestratorRunResponse> {
  return client.post<OrchestratorRunResponse>(
    "/api/autonomy/runs",
    buildStartAutopilotPayload(projectId, toggles, advancedConfig, presetId),
  );
}

export function pauseAutopilotRun(runId: string, client: ApiClient = api): Promise<{ id: string; status: string; paused: boolean }> {
  return client.post(`/api/autonomy/runs/${encodeURIComponent(runId)}/pause`, {});
}

export function resumeAutopilotRun(runId: string, client: ApiClient = api): Promise<OrchestratorRunResponse> {
  return client.post(`/api/autonomy/runs/${encodeURIComponent(runId)}/resume`, {});
}

export function cancelAutopilotRun(
  runId: string,
  stopReason = "cancelled by user",
  client: ApiClient = api,
): Promise<{ id: string; status: string; paused: boolean; stop_reason?: string }> {
  return client.post(`/api/autonomy/runs/${encodeURIComponent(runId)}/cancel`, { stop_reason: stopReason });
}

export function retryAutopilotRun(runId: string, client: ApiClient = api): Promise<OrchestratorRunResponse> {
  return client.post(`/api/autonomy/runs/${encodeURIComponent(runId)}/retry`, {});
}

export function fetchPendingGovernedActions(projectId: string, client: ApiClient = api): Promise<AutonomyPendingAction[]> {
  return client
    .get<{ pending_actions: AutonomyPendingAction[] }>(`/api/autonomy/pending-actions?project_id=${encodeURIComponent(projectId)}`)
    .then((payload) => payload.pending_actions);
}

export function resolveGovernedApproval(
  approvalId: string,
  decision: "approve" | "reject",
  client: ApiClient = api,
): Promise<{ applied: boolean; status: string; reason?: string }> {
  return client.post(`/api/autonomy/pending-actions/${encodeURIComponent(approvalId)}/resolve`, { decision });
}

export function fetchAutonomyAuditLedger(projectId: string, runId?: string, client: ApiClient = api): Promise<AutonomyAuditEntry[]> {
  const params = new URLSearchParams({ project_id: projectId });
  if (runId) params.set("run_id", runId);
  return client.get<{ entries: AutonomyAuditEntry[] }>(`/api/autonomy/audit-ledger?${params}`).then((payload) => payload.entries);
}

export function startOrchestratorRun(
  projectId: string,
  toggles: Partial<Record<string, boolean>>,
  recipe?: RecipeLaunchInputs,
  client: ApiClient = api,
): Promise<OrchestratorRunResponse> {
  return client.post<OrchestratorRunResponse>("/api/orchestrator/runs", buildStartRunPayload(projectId, toggles, recipe));
}

export function startLiteratureReviewRun(
  projectId: string,
  input: LiteratureReviewFormInput,
  client: ApiClient = api,
): Promise<OrchestratorRunResponse> {
  return client.post<OrchestratorRunResponse>(
    "/api/recipes/literature-review/runs",
    buildLiteratureReviewPayload(projectId, input),
  );
}

export function fetchOrchestratorRun(runId: string, client: ApiClient = api): Promise<OrchestratorRunResponse> {
  return client.get<OrchestratorRunResponse>(`/api/agent/runs/${encodeURIComponent(runId)}`);
}

export function cancelAgentRun(runId: string, client: ApiClient = api): Promise<{ id: string; status: string; stop_reason?: string }> {
  return client.post<{ id: string; status: string }>(`/api/agent/runs/${encodeURIComponent(runId)}/cancel`, {});
}

export function requestLiteratureReviewSave(
  runId: string,
  destination: "work/reviews" | "knowledge/literature",
  filename: string,
  client: ApiClient = api,
): Promise<{ approval_id: string; artifact_preview: string; target_relative_path: string }> {
  return client.post("/api/recipes/literature-review/artifacts/save", {
    run_id: runId,
    destination,
    filename,
  });
}

export function resolveLiteratureReviewSave(
  approvalId: string,
  decision: "approve" | "reject",
  client: ApiClient = api,
): Promise<{ applied: boolean; status: string; path?: string | null; reason?: string }> {
  return client.post(`/api/recipes/literature-review/saves/${encodeURIComponent(approvalId)}/resolve`, {
    decision,
  });
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

function inRange(value: number, min: number, max: number): boolean {
  return Number.isFinite(value) && value >= min && value <= max;
}

function includes<T extends readonly string[]>(values: T, value: unknown): value is T[number] {
  return values.includes(String(value));
}
