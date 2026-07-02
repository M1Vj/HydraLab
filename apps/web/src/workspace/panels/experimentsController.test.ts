import { describe, expect, test } from "bun:test";
import {
  buildCreateRunPayload,
  canApprove,
  canPauseOrCancel,
  canRollback,
  canStart,
  derivePanelState,
  isTerminal,
  runControlsEnabled,
  selectableBackends,
  statusLabel,
  type ComputeBackend,
  type ExecutionSetting,
  type ExperimentRun,
} from "./experimentsController";

const run = (over: Partial<ExperimentRun>): ExperimentRun => ({
  id: "r",
  project_id: "p",
  backend_id: "b",
  label: "exp",
  status: "awaiting_approval",
  reason: "",
  config: {},
  checkpoint_ref: null,
  metrics: {},
  enforcement: "seatbelt",
  exit_code: null,
  approval_id: "a",
  review_item_id: null,
  created_at: 0,
  ended_at: null,
  ...over,
});

const setting = (over: Partial<ExecutionSetting>): ExecutionSetting => ({
  project_id: "p",
  execution_enabled: true,
  cloud_budget_usd: null,
  cloud_spend_approved: false,
  ...over,
});

describe("terminal + status labels", () => {
  test("killed:<reason> is terminal and labelled", () => {
    expect(isTerminal("killed:timeout")).toBe(true);
    expect(statusLabel("killed:network")).toBe("Killed (network)");
  });
  test("succeeded terminal, running not", () => {
    expect(isTerminal("succeeded")).toBe(true);
    expect(isTerminal("running")).toBe(false);
    expect(statusLabel("awaiting_approval")).toBe("Awaiting approval");
  });
});

describe("panel state (DEC-12, scenario 8)", () => {
  test("execution disabled -> permission-denied regardless of runs", () => {
    expect(derivePanelState({ loading: false, error: null, executionEnabled: false, runCount: 5 })).toBe(
      "permission-denied",
    );
  });
  test("loading and failure win over content", () => {
    expect(derivePanelState({ loading: true, error: null, executionEnabled: true, runCount: 0 })).toBe("loading");
    expect(derivePanelState({ loading: false, error: new Error("x"), executionEnabled: true, runCount: 3 })).toBe(
      "failure",
    );
  });
  test("enabled + no runs -> empty; enabled + runs -> ready", () => {
    expect(derivePanelState({ loading: false, error: null, executionEnabled: true, runCount: 0 })).toBe("empty");
    expect(derivePanelState({ loading: false, error: null, executionEnabled: true, runCount: 2 })).toBe("ready");
  });
});

describe("run controls gate on execution enablement (HL-SAFE-17)", () => {
  test("controls inert until execution enabled", () => {
    expect(runControlsEnabled(setting({ execution_enabled: false }))).toBe(false);
    expect(runControlsEnabled(null)).toBe(false);
    expect(canStart(run({}), setting({ execution_enabled: false }))).toBe(false);
    expect(canStart(run({}), setting({ execution_enabled: true }))).toBe(true);
  });
  test("a review-inbox run can never be started or approved (HL-SAFE-18)", () => {
    const inboxRun = run({ review_item_id: "ri", approval_id: null });
    expect(canApprove(inboxRun)).toBe(false);
    expect(canStart(inboxRun, setting({ execution_enabled: true }))).toBe(false);
  });
  test("pause/cancel only while active; rollback only after a checkpointed terminal", () => {
    expect(canPauseOrCancel(run({ status: "running" }))).toBe(true);
    expect(canPauseOrCancel(run({ status: "succeeded" }))).toBe(false);
    expect(canRollback(run({ status: "failed", checkpoint_ref: "cp" }))).toBe(true);
    expect(canRollback(run({ status: "failed", checkpoint_ref: null }))).toBe(false);
    expect(canRollback(run({ status: "running", checkpoint_ref: "cp" }))).toBe(false);
  });
});

describe("backend selection (HL-SAFE-10)", () => {
  const backends: ComputeBackend[] = [
    { id: "1", kind: "local_sandbox", display_name: "Local", enabled: true, capabilities: {}, default_limits: {} },
    { id: "2", kind: "cloud", display_name: "modal-a100", enabled: false, capabilities: {}, default_limits: {} },
  ];
  test("disabled backends are not selectable", () => {
    expect(selectableBackends(backends).map((b) => b.id)).toEqual(["1"]);
  });
});

describe("create-run payload", () => {
  test("wraps argv as a vector and carries trust origin", () => {
    const payload = buildCreateRunPayload({ projectId: "p", backendId: "b", label: "exp", argv: ["python3", "x.py"] });
    expect(payload.config).toEqual({ argv: ["python3", "x.py"] });
    expect(payload.trust_origin).toBe("user");
  });
});
