import { describe, expect, test } from "bun:test";
import type { ApiClient } from "../../lib/api";
import {
  BUILTIN_RECIPE_IDS,
  CANONICAL_STAGE_IDS,
  ADVANCED_RUN_PRESETS,
  buildAdvancedRunConfig,
  buildLiteratureReviewPayload,
  buildStartRunPayload,
  buildStartAutopilotPayload,
  fetchOrchestratorStages,
  fetchRecipes,
  startAutopilotRun,
  startLiteratureReviewRun,
  startOrchestratorRun,
  summarizeRunState,
  toggleStage,
  validateAdvancedRunConfig,
} from "./agentRunsController";

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

describe("agent runs controller", () => {
  test("exposes exactly the seven canonical stage ids", () => {
    expect(CANONICAL_STAGE_IDS).toEqual([
      "generate",
      "review",
      "compare",
      "evolve",
      "validate",
      "cache",
      "loop_control",
    ]);
  });

  test("buildStartRunPayload includes only stage toggles", () => {
    const payload = buildStartRunPayload("default", { compare: false });
    expect(payload).toEqual({
      project_id: "default",
      enabled_stages: {
        generate: true,
        review: true,
        compare: false,
        evolve: true,
        validate: true,
        cache: true,
        loop_control: true,
      },
    });
    expect(JSON.stringify(payload)).not.toContain("loop_count");
    expect(JSON.stringify(payload)).not.toContain("population");
    expect(JSON.stringify(payload)).not.toContain("stop_condition");
  });

  test("buildStartRunPayload records recipe inputs without loop controls", () => {
    const payload = buildStartRunPayload(
      "default",
      { generate: true, validate: true },
      {
        recipe_id: "paper-critique",
        draft_or_source: { title: "Sparse Attention", text: "draft" },
        target_venue_style: "ACL",
        source_scope: ["src_attention", "src_bert"],
      },
    );

    expect(payload.recipe_id).toBe("paper-critique");
    expect(payload.recipe_inputs).toEqual({
      draft_or_source: { title: "Sparse Attention", text: "draft" },
      target_venue_style: "ACL",
      source_scope: ["src_attention", "src_bert"],
    });
    expect(JSON.stringify(payload)).not.toContain("loop_count");
    expect(JSON.stringify(payload)).not.toContain("stop_condition");
  });

  test("toggleStage preserves stable stage order", () => {
    const toggles = toggleStage({ generate: true, compare: true }, "compare", false);
    expect(Object.keys(toggles)).toEqual(CANONICAL_STAGE_IDS);
    expect(toggles.compare).toBe(false);
  });

  test("fetchOrchestratorStages reads backend stage list", async () => {
    const client = fakeClient((path) => {
      expect(path).toBe("/api/orchestrator/stages");
      return { stages: [{ id: "generate", label: "Generate", enabled: true }] };
    });
    await expect(fetchOrchestratorStages(client)).resolves.toEqual([
      { id: "generate", label: "Generate", enabled: true },
    ]);
  });

  test("fetchRecipes exposes the built-in writing recipes", async () => {
    const client = fakeClient((path) => {
      expect(path).toBe("/api/orchestrator/recipes");
      return { recipes: BUILTIN_RECIPE_IDS.map((id) => ({ id, name: id, stages: [] })) };
    });
    await expect(fetchRecipes(client)).resolves.toEqual([
      { id: "paper-critique", name: "paper-critique", stages: [] },
      { id: "related-work", name: "related-work", stages: [] },
    ]);
  });

  test("startOrchestratorRun posts the bounded run request", async () => {
    const captured: { path: string; body: unknown } = { path: "", body: null };
    const client = fakeClient((path, body) => {
      captured.path = path;
      captured.body = body;
      return {
        run: { id: "run-1", status: "completed", state: "completed", project_id: "default", mode: "passive", paused: false },
        trace: { run_id: "run-1", steps: [] },
        artifacts: [],
      };
    });

    await startOrchestratorRun("default", { compare: false }, undefined, client);

    expect(captured.path).toBe("/api/orchestrator/runs");
    expect(captured.body).toEqual(buildStartRunPayload("default", { compare: false }));
  });

  test("buildLiteratureReviewPayload includes the bounded recipe input contract", () => {
    const payload = buildLiteratureReviewPayload("default", {
      question: " How does retrieval preserve provenance? ",
      sourceScope: { kind: "all-project" },
      depth: "standard",
      semanticSearch: true,
    });

    expect(payload).toEqual({
      project_id: "default",
      question: "How does retrieval preserve provenance?",
      source_scope: { kind: "all-project" },
      depth: "standard",
      semantic_search: true,
    });
    expect(JSON.stringify(payload)).not.toContain("loop_count");
    expect(JSON.stringify(payload)).not.toContain("stop_condition");
  });

  test("startLiteratureReviewRun posts to the literature recipe endpoint", async () => {
    const captured: { path: string; body: unknown } = { path: "", body: null };
    const client = fakeClient((path, body) => {
      captured.path = path;
      captured.body = body;
      return {
        run: { id: "run-lit", status: "blocked", state: "awaiting_approval", project_id: "default", mode: "copilot", paused: false },
        trace: { run_id: "run-lit", steps: [] },
        artifacts: [],
      };
    });

    await startLiteratureReviewRun("default", {
      question: "What gaps remain?",
      sourceScope: { kind: "source-ids", source_ids: ["src_1"] },
      depth: "quick",
      semanticSearch: false,
    }, client);

    expect(captured.path).toBe("/api/recipes/literature-review/runs");
    expect(captured.body).toEqual({
      project_id: "default",
      question: "What gaps remain?",
      source_scope: { kind: "source-ids", source_ids: ["src_1"] },
      depth: "quick",
      semantic_search: false,
    });
  });

  test("buildAdvancedRunConfig expands presets losslessly", () => {
    const deep = buildAdvancedRunConfig("deep");

    expect(deep).toEqual(ADVANCED_RUN_PRESETS.deep);
    expect(Object.keys(deep)).toEqual([
      "candidate_count",
      "population_size",
      "compare_enabled",
      "ranking_method",
      "review_depth",
      "evolution_method",
      "validation_rules",
      "max_loop_iterations",
      "stop_conditions",
      "budget_policy",
      "checkpoint_frequency",
    ]);
  });

  test("validateAdvancedRunConfig rejects bad values with field and allowed set within 200ms", () => {
    const started = performance.now();
    const result = validateAdvancedRunConfig({ ...buildAdvancedRunConfig(), population_size: 1001 });
    const elapsed = performance.now() - started;

    expect(result.state).toBe("failure");
    expect(result.error?.field).toBe("population_size");
    expect(result.error?.allowed).toBe("1..100");
    expect(elapsed).toBeLessThan(200);
  });

  test("validateAdvancedRunConfig reports permission denied when Autopilot is unavailable", () => {
    const result = validateAdvancedRunConfig(buildAdvancedRunConfig(), { autopilotEnabled: false });

    expect(result.state).toBe("permission-denied");
  });

  test("buildStartAutopilotPayload includes advanced config without changing stage toggles", () => {
    const advanced = buildAdvancedRunConfig("strict_evidence", { ranking_method: "elo" });
    const payload = buildStartAutopilotPayload("default", { compare: false }, advanced, "strict_evidence");

    expect(payload.enabled_stages.compare).toBe(false);
    expect(payload.advanced_preset_id).toBe("strict_evidence");
    expect(payload.advanced_config?.ranking_method).toBe("elo");
    expect(payload.advanced_config?.validation_rules).toEqual(["typecheck", "lint", "test", "build"]);
  });

  test("startAutopilotRun posts the advanced payload when supplied", async () => {
    const advanced = buildAdvancedRunConfig("balanced", { ranking_method: "rubric" });
    const captured: { path: string; body: unknown } = { path: "", body: null };
    const client = fakeClient((path, body) => {
      captured.path = path;
      captured.body = body;
      return {
        run: { id: "run-auto", status: "completed", state: "completed", project_id: "default", mode: "full_access", paused: false },
        trace: { run_id: "run-auto", steps: [] },
        artifacts: [],
      };
    });

    await startAutopilotRun("default", { compare: true }, client, advanced);

    expect(captured.path).toBe("/api/autonomy/runs");
    expect(captured.body).toEqual(buildStartAutopilotPayload("default", { compare: true }, advanced));
  });

  test("summarizeRunState surfaces budget and offline stops", () => {
    expect(summarizeRunState("blocked", "budget_blocked")).toBe("Budget blocked");
    expect(summarizeRunState("permission-denied", "permission-denied")).toBe("Permission denied");
    expect(summarizeRunState("completed")).toBe("Completed");
  });
});
