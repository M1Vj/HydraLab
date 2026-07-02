import { describe, expect, test } from "bun:test";
import { HydraApiError, type ApiClient, type IdeaCandidate, type IdeaRunResponse } from "../../lib/api";
import {
  IDEA_STAGE_IDS,
  IDEA_STATE_MESSAGES,
  buildIdeaRunPayload,
  completedStagePrefix,
  defaultIdeaToggles,
  deriveIdeaBoardState,
  fetchIdeaRun,
  hasRubricScores,
  promoteCandidate,
  rankedCandidates,
  resolveIdeaPromotion,
  startIdeaRun,
  toggleIdeaStage,
} from "./ideaBoardController";

function fakeClient(handler: (path: string, body?: unknown) => unknown): ApiClient {
  return {
    get: async <T,>(path: string) => handler(path) as T,
    post: async <T,>(path: string, body?: unknown) => handler(path, body) as T,
    put: async <T,>(path: string, body?: unknown) => handler(path, body) as T,
    patch: async <T,>(path: string, body?: unknown) => handler(path, body) as T,
    delete: async <T,>(path: string) => handler(path) as T,
    stream: async () => undefined,
  } as unknown as ApiClient;
}

function candidate(partial: Partial<IdeaCandidate>): IdeaCandidate {
  return {
    id: "c1",
    run_id: "run-1",
    title: "Idea",
    short_hypothesis: "",
    research_question: "",
    motivation: "",
    method_sketch: "",
    expected_contribution: "",
    required_sources: [],
    evidence_links: [],
    novelty_claim: "",
    feasibility_notes: "",
    risks: "",
    estimated_effort: "",
    generated_by_stage: "generate",
    parent_candidate_id: null,
    status: "ranked",
    critique: {},
    rubric_results: [],
    rank: null,
    trust_origin: "user",
    ...partial,
  };
}

function run(partial: Partial<IdeaRunResponse> & { steps?: IdeaRunResponse["trace"]["steps"] } = {}): IdeaRunResponse {
  return {
    run: { id: "run-1", project_id: "default", mode: "passive", status: "completed", state: "completed", paused: false },
    trace: { run_id: "run-1", steps: partial.steps ?? [] },
    artifacts: [],
    candidates: partial.candidates ?? [],
    ...("run" in partial ? { run: partial.run! } : {}),
  };
}

describe("idea board controller", () => {
  test("exposes exactly the four toggleable stages and no loop controls", () => {
    expect(IDEA_STAGE_IDS).toEqual(["generate", "review", "compare", "evolve"]);
    const payload = buildIdeaRunPayload("default", { topic: "attention" }, { compare: false });
    expect(payload.enabled_stages).toEqual({ generate: true, review: true, compare: false, evolve: false });
    const serialized = JSON.stringify(payload);
    expect(serialized).not.toContain("loop_count");
    expect(serialized).not.toContain("population");
    expect(serialized).not.toContain("stop_condition");
  });

  test("default toggles keep Generate and Review on and Evolve off", () => {
    expect(defaultIdeaToggles()).toEqual({ generate: true, review: true, compare: true, evolve: false });
  });

  test("toggleIdeaStage preserves stable stage order", () => {
    const toggles = toggleIdeaStage({ generate: true }, "evolve", true);
    expect(Object.keys(toggles)).toEqual([...IDEA_STAGE_IDS]);
    expect(toggles.evolve).toBe(true);
  });

  test("startIdeaRun posts the recipe run request with the input schema", async () => {
    const captured: { path: string; body: unknown } = { path: "", body: null };
    const client = fakeClient((path, body) => {
      captured.path = path;
      captured.body = body;
      return run();
    });
    await startIdeaRun("default", { topic: "sub-quadratic attention", novelty_target: "high" }, {}, client);
    expect(captured.path).toBe("/api/recipes/idea/runs");
    expect(captured.body).toMatchObject({ project_id: "default", topic: "sub-quadratic attention", novelty_target: "high" });
  });

  test("fetchIdeaRun and promotion helpers hit the recipe routes", async () => {
    const paths: string[] = [];
    const client = fakeClient((path) => {
      paths.push(path);
      return { status: "review_inbox" };
    });
    await fetchIdeaRun("run-9", client);
    await promoteCandidate("default", "cand-1", "task", client);
    await resolveIdeaPromotion("ri-1", "approve", client);
    expect(paths).toEqual([
      "/api/recipes/idea/runs/run-9",
      "/api/recipes/idea/promote",
      "/api/recipes/idea/promotions/ri-1/resolve",
    ]);
  });

  test("empty state message prompts running the slash command", () => {
    const state = deriveIdeaBoardState({ loading: false, error: null, run: null });
    expect(state.kind).toBe("empty");
    expect(state.message).toBe(IDEA_STATE_MESSAGES.empty);
  });

  test("loading state renders while a run streams", () => {
    const state = deriveIdeaBoardState({ loading: true, error: null, run: null });
    expect(state.kind).toBe("loading");
  });

  test("permission-denied surfaces for offline-blocked runs", () => {
    const offlineRun = run({
      steps: [{ index: 0, kind: "consent.offline_blocked", status: "blocked", summary: "", tokens: 0, trust_origin: "user" }],
    });
    offlineRun.run.status = "blocked";
    offlineRun.run.state = "permission-denied";
    const state = deriveIdeaBoardState({ loading: false, error: null, run: offlineRun });
    expect(state.kind).toBe("permission-denied");
    expect(state.message).toBe(IDEA_STATE_MESSAGES.permissionDenied);
  });

  test("permission-denied surfaces for consent-gate api errors", () => {
    const error = new HydraApiError({ kind: "permission-denied", message: "blocked" });
    const state = deriveIdeaBoardState({ loading: false, error, run: null });
    expect(state.kind).toBe("permission-denied");
  });

  test("mid-stream failure keeps the completed-stage prefix", () => {
    const failedRun = run({
      steps: [
        { index: 0, kind: "stage.generate", status: "completed", summary: "", tokens: 0, trust_origin: "user" },
        { index: 1, kind: "stage.review", status: "completed", summary: "", tokens: 0, trust_origin: "user" },
        { index: 2, kind: "stage.compare", status: "failed", summary: "provider error", tokens: 0, trust_origin: "user" },
      ],
      candidates: [candidate({ status: "reviewed" })],
    });
    failedRun.run.status = "failed";
    failedRun.run.state = "failed";
    const state = deriveIdeaBoardState({ loading: false, error: null, run: failedRun });
    expect(state.kind).toBe("failure");
    expect(state.completedStages).toEqual(["generate", "review"]);
    expect(completedStagePrefix(failedRun.trace.steps)).toEqual(["generate", "review"]);
  });

  test("Compare-off candidates render unranked with no score column", () => {
    const unranked = [candidate({ id: "a", rank: null }), candidate({ id: "b", rank: null })];
    expect(hasRubricScores(unranked)).toBe(false);
    expect(rankedCandidates(unranked).map((c) => c.id)).toEqual(["a", "b"]);
  });

  test("ranked candidates sort by rank and expose rubric scores", () => {
    const ranked = [
      candidate({ id: "low", rank: 2, rubric_results: [{ criterion: "novelty", value: 0.5, rationale: "x", stage_run_id: "s", source_refs: [] }] }),
      candidate({ id: "top", rank: 1, rubric_results: [{ criterion: "novelty", value: 0.9, rationale: "x", stage_run_id: "s", source_refs: [] }] }),
    ];
    expect(hasRubricScores(ranked)).toBe(true);
    expect(rankedCandidates(ranked).map((c) => c.id)).toEqual(["top", "low"]);
  });
});
