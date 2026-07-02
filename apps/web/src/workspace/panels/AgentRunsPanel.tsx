import { useEffect, useMemo, useState } from "react";
import { Boxes, CheckCircle2, CircleDashed, FileText, ListRestart, PauseCircle, Play, RefreshCcw, RotateCcw, Save, SkipForward, SlidersHorizontal, XCircle } from "lucide-react";
import type { AgentRunArtifact, AgentTraceStep, AutonomyAuditEntry, AutonomyPendingAction, AutonomyPolicy, OrchestratorRunResponse, OrchestratorStage } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { FailureState, LoadingState, PanelScaffold } from "./PanelState";
import {
  CANONICAL_STAGE_IDS,
  ADVANCED_EVOLUTION_METHODS,
  ADVANCED_RANKING_METHODS,
  ADVANCED_RUN_PRESETS,
  ADVANCED_STOP_CONDITIONS,
  ADVANCED_VALIDATION_RULES,
  buildAdvancedRunConfig,
  cancelAgentRun,
  defaultStageToggles,
  cancelAutopilotRun,
  fetchAutonomyAuditLedger,
  fetchAutonomyPolicy,
  fetchOrchestratorStages,
  fetchPendingGovernedActions,
  fetchRecipes,
  pauseAutopilotRun,
  requestLiteratureReviewSave,
  resolveGovernedApproval,
  resolveLiteratureReviewSave,
  resumeAutopilotRun,
  retryAutopilotRun,
  saveAutonomyPolicy,
  startAutopilotRun,
  stageStatus,
  startLiteratureReviewRun,
  startOrchestratorRun,
  summarizeRunState,
  toggleStage,
  validateAdvancedRunConfig,
  type AdvancedRunConfig,
  type AdvancedValidationResult,
  type BuiltinRecipeId,
  type LiteratureDepth,
  type RecipeDescriptor,
  type StageId,
  type StageToggles,
} from "./agentRunsController";

const LITERATURE_RECIPE_ID = "literature-review";

const PROJECT_ID = "default";

function statusIcon(status: string) {
  if (status === "completed") return <CheckCircle2 size={14} aria-hidden />;
  if (status === "skipped") return <SkipForward size={14} aria-hidden />;
  return <CircleDashed size={14} aria-hidden />;
}

export function AgentRunsPanel({ announce }: PanelComponentProps) {
  const [stages, setStages] = useState<OrchestratorStage[]>([]);
  const [recipes, setRecipes] = useState<RecipeDescriptor[]>([]);
  const [selectedRecipe, setSelectedRecipe] = useState<BuiltinRecipeId | string>("paper-critique");
  const [draftTitle, setDraftTitle] = useState("Sparse Attention for Long Documents");
  const [draftText, setDraftText] = useState("");
  const [targetVenueStyle, setTargetVenueStyle] = useState("ACL");
  const [sourceScope, setSourceScope] = useState("");
  const [toggles, setToggles] = useState<StageToggles>(() => defaultStageToggles());
  const [run, setRun] = useState<OrchestratorRunResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [question, setQuestion] = useState("");
  const [scopeText, setScopeText] = useState("");
  const [depth, setDepth] = useState<LiteratureDepth>("standard");
  const [semanticSearch, setSemanticSearch] = useState(false);
  const [saveDestination, setSaveDestination] = useState<"work/reviews" | "knowledge/literature">("work/reviews");
  const [saveFilename, setSaveFilename] = useState("");
  const [saveStatus, setSaveStatus] = useState("");
  const [autonomyPolicy, setAutonomyPolicy] = useState<AutonomyPolicy | null>(null);
  const [pendingActions, setPendingActions] = useState<AutonomyPendingAction[]>([]);
  const [auditEntries, setAuditEntries] = useState<AutonomyAuditEntry[]>([]);
  const [governanceBusy, setGovernanceBusy] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [advancedPreset, setAdvancedPreset] = useState("balanced");
  const [advancedConfig, setAdvancedConfig] = useState<AdvancedRunConfig>(() => buildAdvancedRunConfig("balanced"));
  const [advancedTouched, setAdvancedTouched] = useState(false);
  const [advancedValidation, setAdvancedValidation] = useState<AdvancedValidationResult>({ state: "empty", error: null });

  const recipeOptions = useMemo<RecipeDescriptor[]>(() => {
    const base = recipes.length ? recipes : [{ id: "paper-critique", name: "Paper Critique", stages: [] }];
    return base.some((recipe) => recipe.id === LITERATURE_RECIPE_ID)
      ? base
      : [{ id: LITERATURE_RECIPE_ID, name: "Literature Review", stages: [] }, ...base];
  }, [recipes]);
  const isLiteratureReview = selectedRecipe === LITERATURE_RECIPE_ID;

  useEffect(() => {
    void loadStages();
  }, []);

  useEffect(() => {
    if (!advancedOpen) return;
    setAdvancedValidation({ state: "loading", error: null });
    const timer = window.setTimeout(() => {
      const result = validateAdvancedRunConfig(advancedConfig, { autopilotEnabled: Boolean(autonomyPolicy?.autopilot_enabled) });
      setAdvancedValidation(!advancedTouched && result.state === "ready" ? { state: "empty", error: null } : result);
    }, 25);
    return () => window.clearTimeout(timer);
  }, [advancedConfig, advancedOpen, advancedTouched, autonomyPolicy?.autopilot_enabled]);

  async function loadStages() {
    setLoading(true);
    setError(null);
    try {
      const [loaded, loadedRecipes, policy, pending, audit] = await Promise.all([
        fetchOrchestratorStages(),
        fetchRecipes(),
        fetchAutonomyPolicy(PROJECT_ID),
        fetchPendingGovernedActions(PROJECT_ID),
        fetchAutonomyAuditLedger(PROJECT_ID),
      ]);
      setStages(loaded);
      setRecipes(loadedRecipes);
      setAutonomyPolicy(policy);
      setPendingActions(pending);
      setAuditEntries(audit);
      setToggles((current) => {
        const next = { ...defaultStageToggles(), ...current };
        for (const stage of loaded) {
          if (CANONICAL_STAGE_IDS.includes(stage.id as StageId)) next[stage.id as StageId] = stage.enabled;
        }
        return next;
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setLoading(false);
    }
  }

  async function startRun() {
    if (autonomyPolicy?.autopilot_enabled) {
      await startAutonomyRun();
      return;
    }
    if (isLiteratureReview) {
      await startLiteratureRun();
      return;
    }
    await startRecipeRun();
  }

  async function startAutonomyRun() {
    if (!autonomyPolicy) return;
    setRunning(true);
    setError(null);
    try {
      const saved = await saveAutonomyPolicy({ ...autonomyPolicy, project_id: PROJECT_ID });
      setAutonomyPolicy(saved);
      const validation: AdvancedValidationResult = advancedOpen
        ? validateAdvancedRunConfig(advancedConfig, { autopilotEnabled: Boolean(saved.autopilot_enabled) })
        : { state: "ready", error: null };
      if (validation.state === "failure") {
        setAdvancedValidation(validation);
        setError(new Error(`${validation.error?.field}: allowed ${validation.error?.allowed}`));
        return;
      }
      if (validation.state === "permission-denied") {
        setAdvancedValidation(validation);
        return;
      }
      const started = await startAutopilotRun(
        PROJECT_ID,
        toggles,
        undefined,
        advancedOpen ? advancedConfig : undefined,
        advancedPreset,
      );
      setRun(started);
      await refreshGovernance(started.run.id);
      announce(`Autopilot ${summarizeRunState(started.run.status, started.run.state).toLowerCase()}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setRunning(false);
    }
  }

  async function startLiteratureRun() {
    if (!question.trim()) {
      setError(new Error("Enter a research question to start the review."));
      return;
    }
    setRunning(true);
    setError(null);
    setSaveStatus("");
    try {
      const started = await startLiteratureReviewRun(PROJECT_ID, {
        question,
        sourceScope: parseSourceScope(scopeText),
        depth,
        semanticSearch,
      });
      setRun(started);
      announce(`Literature review ${summarizeRunState(started.run.status, started.run.state).toLowerCase()}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setRunning(false);
    }
  }

  async function startRecipeRun() {
    setRunning(true);
    setError(null);
    try {
      const recipe = recipes.find((item) => item.id === selectedRecipe);
      const recipeStages = recipe?.stages?.length
        ? Object.fromEntries(CANONICAL_STAGE_IDS.map((id) => [id, recipe.stages.includes(id)]))
        : toggles;
      const started = await startOrchestratorRun(PROJECT_ID, recipeStages, {
        recipe_id: selectedRecipe,
        draft_or_source: { title: draftTitle, text: draftText },
        target_venue_style: targetVenueStyle,
        source_scope: sourceScope.split(",").map((item) => item.trim()).filter(Boolean),
      });
      setRun(started);
      dispatchRelatedWorkSuggestion(started.artifacts);
      announce(`Run ${summarizeRunState(started.run.status, started.run.state).toLowerCase()}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setRunning(false);
    }
  }

  async function cancelRun() {
    if (!run) return;
    try {
      const cancelled = autonomyPolicy?.autopilot_enabled
        ? await cancelAutopilotRun(run.run.id)
        : await cancelAgentRun(run.run.id);
      const next = { ...run, run: { ...run.run, status: "cancelled", state: "cancelled", stop_reason: cancelled.stop_reason } };
      setRun(next);
      announce("Run cancelled");
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  async function pauseRun() {
    if (!run) return;
    try {
      await pauseAutopilotRun(run.run.id);
      setRun({ ...run, run: { ...run.run, status: "paused", paused: true } });
      announce("Autopilot paused");
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  async function resumeRun() {
    if (!run) return;
    try {
      const resumed = await resumeAutopilotRun(run.run.id);
      setRun(resumed);
      await refreshGovernance(resumed.run.id);
      announce("Autopilot resumed");
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  async function retryRun() {
    if (!run) return;
    try {
      const retried = await retryAutopilotRun(run.run.id);
      setRun(retried);
      await refreshGovernance(retried.run.id);
      announce("Autopilot retried");
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  async function refreshGovernance(runId = run?.run.id) {
    setGovernanceBusy(true);
    try {
      const [pending, audit] = await Promise.all([
        fetchPendingGovernedActions(PROJECT_ID),
        fetchAutonomyAuditLedger(PROJECT_ID, runId),
      ]);
      setPendingActions(pending);
      setAuditEntries(audit);
    } finally {
      setGovernanceBusy(false);
    }
  }

  async function resolveGovernedAction(action: AutonomyPendingAction, decision: "approve" | "reject") {
    if (action.kind !== "approval") return;
    try {
      await resolveGovernedApproval(action.id, decision);
      await refreshGovernance();
      announce(decision === "approve" ? "Governed action approved" : "Governed action rejected");
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  async function resolveSave(decision: "approve" | "reject") {
    if (!run) return;
    setSaveStatus("");
    try {
      const pending = await requestLiteratureReviewSave(run.run.id, saveDestination, saveFilename);
      const resolved = await resolveLiteratureReviewSave(pending.approval_id, decision);
      setSaveStatus(
        decision === "approve" && resolved.applied
          ? `Saved to ${resolved.path ?? pending.target_relative_path}`
          : "Save declined; no review file was written.",
      );
      announce(decision === "approve" && resolved.applied ? "Literature review saved" : "Literature review save declined");
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  function onToggle(stage: StageId, enabled: boolean) {
    setToggles((current) => toggleStage(current, stage, enabled));
  }

  function updateAutonomyPolicy(patch: Partial<AutonomyPolicy>) {
    setAutonomyPolicy((current) => current ? { ...current, ...patch } : current);
  }

  function updateAdvancedConfig(patch: Partial<AdvancedRunConfig>) {
    setAdvancedTouched(true);
    setAdvancedConfig((current) => buildAdvancedRunConfig(advancedPreset, { ...current, ...patch }));
  }

  function updateBudgetPolicy(patch: Partial<AdvancedRunConfig["budget_policy"]>) {
    setAdvancedTouched(true);
    setAdvancedConfig((current) => ({
      ...current,
      budget_policy: { ...current.budget_policy, ...patch },
    }));
  }

  function updateAdvancedPreset(preset: string) {
    setAdvancedPreset(preset);
    setAdvancedConfig(buildAdvancedRunConfig(preset));
    setAdvancedTouched(false);
  }

  const steps = run?.trace.steps ?? [];
  const artifacts = run?.artifacts ?? [];
  const literatureArtifact = artifacts.find((artifact) => artifact.kind === "literature-review");
  const banner = useMemo(
    () => (run ? summarizeRunState(run.run.status, run.run.state) : "Ready"),
    [run],
  );

  if (loading) return <LoadingState title="Loading agent runs" />;
  if (error) return <FailureState error={error} onRetry={loadStages} />;

  return (
    <PanelScaffold title="Agent Runs">
      <div className="agent-runs-panel">
        <header className="agent-runs-header">
          <div>
            {isLiteratureReview ? (
              <>
                <h2>Literature review</h2>
                <p>Fixed Generate, Review, Validate, Cache pass</p>
              </>
            ) : (
              <>
                <h2>Recipe run</h2>
                <p>Bounded Phase-2 pass with approval gates</p>
              </>
            )}
          </div>
          <button type="button" className="primary-action compact" onClick={() => void startRun()} disabled={running}>
            {running ? <RefreshCcw size={14} aria-hidden /> : <Play size={14} aria-hidden />}
            {running ? "Running" : isLiteratureReview ? "Start review" : "Start run"}
          </button>
        </header>

        <section className="agent-recipe-picker" aria-label="Recipe selector">
          <label>
            <span>Recipe</span>
            <select value={selectedRecipe} onChange={(event) => setSelectedRecipe(event.target.value)}>
              {recipeOptions.map((recipe) => (
                <option key={recipe.id} value={recipe.id}>
                  {recipe.name}
                </option>
              ))}
            </select>
          </label>
          {autonomyPolicy && (
            <div className="autonomy-policy-strip" aria-label="Autopilot governance">
              <label>
                <span>Mode</span>
                <select value={autonomyPolicy.mode} onChange={(event) => updateAutonomyPolicy({ mode: event.target.value })}>
                  <option value="passive">Passive</option>
                  <option value="copilot">Co-pilot</option>
                  <option value="full_access">Full Access</option>
                </select>
              </label>
              <label>
                <span>Max loops</span>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={autonomyPolicy.max_loop_count}
                  onChange={(event) => updateAutonomyPolicy({ max_loop_count: Number(event.target.value) || 1 })}
                />
              </label>
              <label className="agent-inline-toggle">
                <input
                  type="checkbox"
                  checked={autonomyPolicy.autopilot_enabled}
                  onChange={(event) => updateAutonomyPolicy({ autopilot_enabled: event.target.checked })}
                />
                <span>Autopilot</span>
              </label>
            </div>
          )}
        </section>

        {isLiteratureReview && (
          <section className="literature-review-form" aria-label="Literature review recipe">
            <label>
              <span>Question</span>
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                rows={3}
                placeholder="How do transformer attention mechanisms scale with sequence length?"
              />
            </label>
            <div className="literature-review-grid">
              <label>
                <span>Source scope</span>
                <input
                  value={scopeText}
                  onChange={(event) => setScopeText(event.target.value)}
                  placeholder="All saved sources or comma-separated source ids"
                />
              </label>
              <label>
                <span>Depth</span>
                <select value={depth} onChange={(event) => setDepth(event.target.value as LiteratureDepth)}>
                  <option value="quick">Quick</option>
                  <option value="standard">Standard</option>
                  <option value="deep">Deep</option>
                </select>
              </label>
            </div>
            <label className="agent-inline-toggle">
              <input type="checkbox" checked={semanticSearch} onChange={(event) => setSemanticSearch(event.target.checked)} />
              <span>Semantic retrieval</span>
            </label>
          </section>
        )}

        {autonomyPolicy && (
          <AdvancedRunDisclosure
            open={advancedOpen}
            onOpenChange={setAdvancedOpen}
            preset={advancedPreset}
            config={advancedConfig}
            validation={advancedValidation}
            onPresetChange={updateAdvancedPreset}
            onConfigChange={updateAdvancedConfig}
            onBudgetChange={updateBudgetPolicy}
          />
        )}

        <div className={`agent-run-banner ${run?.run.status ?? "idle"}`} role="status">
          <ListRestart size={15} aria-hidden />
          <strong>{banner}</strong>
          {run && <span>{run.run.mode} - {run.trace.steps.length} events</span>}
          {run?.run.stop_reason && <span>Stop: {run.run.stop_reason}</span>}
          {run && autonomyPolicy?.autopilot_enabled && run.run.status === "running" && (
            <button type="button" className="icon-text-action" onClick={() => void pauseRun()}>
              <PauseCircle size={14} aria-hidden /> Pause
            </button>
          )}
          {run && autonomyPolicy?.autopilot_enabled && run.run.status === "paused" && (
            <button type="button" className="icon-text-action" onClick={() => void resumeRun()}>
              <Play size={14} aria-hidden /> Resume
            </button>
          )}
          {run && autonomyPolicy?.autopilot_enabled && ["cancelled", "failed", "blocked"].includes(run.run.status) && (
            <button type="button" className="icon-text-action" onClick={() => void retryRun()}>
              <RotateCcw size={14} aria-hidden /> Retry
            </button>
          )}
          {run && ["running", "paused", "blocked"].includes(run.run.status) && (
            <button type="button" className="icon-text-action" onClick={() => void cancelRun()}>
              <XCircle size={14} aria-hidden /> Cancel
            </button>
          )}
        </div>

        {!isLiteratureReview && (
          <section className="agent-recipe-launch" aria-label="Recipe launcher">
            <label>
              Draft or source{" "}
              <input
                type="text"
                value={draftTitle}
                onChange={(event) => setDraftTitle(event.target.value)}
                aria-label="Draft or source title"
              />
            </label>
            <label>
              Target venue/style{" "}
              <input
                type="text"
                value={targetVenueStyle}
                onChange={(event) => setTargetVenueStyle(event.target.value)}
                aria-label="Target venue style"
              />
            </label>
            <label>
              Source scope{" "}
              <input
                type="text"
                value={sourceScope}
                onChange={(event) => setSourceScope(event.target.value)}
                placeholder="source ids, comma separated"
                aria-label="Source scope"
              />
            </label>
            <label>
              Draft text{" "}
              <textarea
                value={draftText}
                onChange={(event) => setDraftText(event.target.value)}
                aria-label="Draft text"
                rows={4}
              />
            </label>
          </section>
        )}

        {!isLiteratureReview && (
          <section className="agent-stage-toggle-list" aria-label="Stage toggles">
            {(stages.length ? stages : CANONICAL_STAGE_IDS.map((id) => ({ id, label: id.replace("_", " "), enabled: true }))).map((stage) => {
              const id = stage.id as StageId;
              if (!CANONICAL_STAGE_IDS.includes(id)) return null;
              return (
                <label key={id} className="agent-stage-toggle">
                  <input type="checkbox" checked={toggles[id]} onChange={(event) => onToggle(id, event.target.checked)} />
                  <span>{stage.label}</span>
                  <small>{stageStatus(steps, id)}</small>
                </label>
              );
            })}
          </section>
        )}

        <section className="agent-run-stream" aria-label="Live event stream">
          <h3>Event stream</h3>
          {steps.length === 0 ? (
            <p className="agent-run-muted">No run events yet.</p>
          ) : (
            <ol>
              {steps.map((step) => <TraceRow key={`${step.index}-${step.kind}`} step={step} />)}
            </ol>
          )}
        </section>

        <section className="agent-run-artifacts" aria-label="Artifacts">
          <h3><Boxes size={14} aria-hidden /> Artifacts</h3>
          {artifacts.length === 0 ? (
            <p className="agent-run-muted">No artifacts yet.</p>
          ) : (
            <ul>
              {artifacts.map((artifact) => <ArtifactRow key={artifact.id} artifact={artifact} />)}
            </ul>
          )}
          {literatureArtifact && (
            <div className="literature-review-preview">
              <h4><FileText size={14} aria-hidden /> Preview</h4>
              <pre>{previewMarkdown(literatureArtifact.markdown)}</pre>
              <div className="literature-save-row">
                <select value={saveDestination} onChange={(event) => setSaveDestination(event.target.value as "work/reviews" | "knowledge/literature")}>
                  <option value="work/reviews">work/reviews</option>
                  <option value="knowledge/literature">knowledge/literature</option>
                </select>
                <input value={saveFilename} onChange={(event) => setSaveFilename(event.target.value)} placeholder="review.md" />
                <button type="button" className="primary-action compact" onClick={() => void resolveSave("approve")}>
                  <Save size={14} aria-hidden /> Approve
                </button>
                <button type="button" className="secondary-action compact" onClick={() => void resolveSave("reject")}>
                  Decline
                </button>
              </div>
              {saveStatus && <p className="agent-run-muted" role="status">{saveStatus}</p>}
            </div>
          )}
        </section>

        <section className="autonomy-governance" aria-label="Run governance">
          <div className="autonomy-section-header">
            <h3>Governance</h3>
            <button type="button" className="icon-text-action" onClick={() => void refreshGovernance()} disabled={governanceBusy}>
              <RefreshCcw size={14} aria-hidden /> Refresh
            </button>
          </div>
          <div className="autonomy-governance-grid">
            <div>
              <h4>Pending actions</h4>
              {pendingActions.length === 0 ? (
                <p className="agent-run-muted">No pending governed actions.</p>
              ) : (
                <ul className="autonomy-action-list">
                  {pendingActions.map((action) => (
                    <li key={`${action.kind}-${action.id}`}>
                      <div>
                        <strong>{action.summary || action.action_kind}</strong>
                        <span>{action.target_ref || action.reason || action.status}</span>
                      </div>
                      <span className={riskBadgeClass(action.risk_level)}>{action.risk_level}</span>
                      {action.kind === "approval" ? (
                        <div className="approval-actions">
                          <button type="button" className="secondary-action compact" onClick={() => void resolveGovernedAction(action, "reject")}>
                            Reject
                          </button>
                          <button type="button" className="primary-action compact" onClick={() => void resolveGovernedAction(action, "approve")}>
                            Approve
                          </button>
                        </div>
                      ) : (
                        <small>Review Inbox</small>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h4>Audit ledger</h4>
              {auditEntries.length === 0 ? (
                <p className="agent-run-muted">No audit entries for this run.</p>
              ) : (
                <ol className="autonomy-audit-list">
                  {auditEntries.map((entry) => (
                    <li key={entry.id}>
                      <span className={riskBadgeClass(entry.risk_level)}>{entry.risk_level}</span>
                      <strong>{entry.action}</strong>
                      <span>{entry.approval_state}</span>
                      <small>{entry.target || entry.actor}</small>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        </section>
      </div>
    </PanelScaffold>
  );
}

function dispatchRelatedWorkSuggestion(artifacts: AgentRunArtifact[]) {
  const relatedWork = artifacts.find((artifact) => artifact.kind === "related-work-draft") as AgentRunArtifact & {
    draft?: { paragraphs?: Array<{ text?: string; trace_links?: unknown[] }> };
  };
  const paragraph = relatedWork?.draft?.paragraphs?.[0];
  if (!paragraph?.text) return;
  window.dispatchEvent(
    new CustomEvent("hydra:related-work-suggestion", {
      detail: {
        text: paragraph.text,
        trace_links: paragraph.trace_links ?? [],
      },
    }),
  );
}

function TraceRow({ step }: { step: AgentTraceStep }) {
  return (
    <li className={`agent-trace-row ${step.status}`}>
      {statusIcon(step.status)}
      <span>{step.kind.replace("stage.", "").replace("_", " ")}</span>
      <small>{step.status}</small>
    </li>
  );
}

function ArtifactRow({ artifact }: { artifact: AgentRunArtifact }) {
  return (
    <li>
      <strong>{artifact.kind}</strong>
      <span>{artifact.summary ?? artifact.ref ?? artifact.id}</span>
      {artifact.ranking && <small>{artifact.ranking.map((item) => item.id).join(" -> ")}</small>}
    </li>
  );
}

function AdvancedRunDisclosure({
  open,
  onOpenChange,
  preset,
  config,
  validation,
  onPresetChange,
  onConfigChange,
  onBudgetChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preset: string;
  config: AdvancedRunConfig;
  validation: AdvancedValidationResult;
  onPresetChange: (preset: string) => void;
  onConfigChange: (patch: Partial<AdvancedRunConfig>) => void;
  onBudgetChange: (patch: Partial<AdvancedRunConfig["budget_policy"]>) => void;
}) {
  return (
    <details className="advanced-run-config" open={open} onToggle={(event) => onOpenChange(event.currentTarget.open)}>
      <summary>
        <SlidersHorizontal size={14} aria-hidden />
        <span>Advanced</span>
        <small className={`advanced-state ${validation.state}`}>{advancedStateLabel(validation)}</small>
      </summary>
      <div className="advanced-run-grid">
        <label>
          <span>Preset</span>
          <select value={preset} onChange={(event) => onPresetChange(event.target.value)}>
            {Object.keys(ADVANCED_RUN_PRESETS).map((id) => (
              <option key={id} value={id}>{id.replace("_", " ")}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Ranking</span>
          <select value={config.ranking_method} onChange={(event) => onConfigChange({ ranking_method: event.target.value as AdvancedRunConfig["ranking_method"] })}>
            {ADVANCED_RANKING_METHODS.map((method) => (
              <option key={method} value={method}>{method}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Candidates</span>
          <input type="number" min={1} max={20} value={config.candidate_count} onChange={(event) => onConfigChange({ candidate_count: Number(event.target.value) })} />
        </label>
        <label>
          <span>Population</span>
          <input type="number" min={1} max={100} value={config.population_size} onChange={(event) => onConfigChange({ population_size: Number(event.target.value) })} />
        </label>
        <label>
          <span>Review depth</span>
          <input type="number" min={1} max={5} value={config.review_depth} onChange={(event) => onConfigChange({ review_depth: Number(event.target.value) })} />
        </label>
        <label>
          <span>Evolution</span>
          <select value={config.evolution_method} onChange={(event) => onConfigChange({ evolution_method: event.target.value as AdvancedRunConfig["evolution_method"] })}>
            {ADVANCED_EVOLUTION_METHODS.map((method) => (
              <option key={method} value={method}>{method}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Loops</span>
          <input type="number" min={1} max={100} value={config.max_loop_iterations} onChange={(event) => onConfigChange({ max_loop_iterations: Number(event.target.value) })} />
        </label>
        <label>
          <span>Checkpoints</span>
          <input type="number" min={1} max={25} value={config.checkpoint_frequency} onChange={(event) => onConfigChange({ checkpoint_frequency: Number(event.target.value) })} />
        </label>
        <label>
          <span>Token budget</span>
          <input type="number" min={1} max={200000} value={config.budget_policy.tokens} onChange={(event) => onBudgetChange({ tokens: Number(event.target.value) })} />
        </label>
        <label>
          <span>Time budget</span>
          <input type="number" min={1} max={3600} value={config.budget_policy.wall_clock_seconds} onChange={(event) => onBudgetChange({ wall_clock_seconds: Number(event.target.value) })} />
        </label>
        <label>
          <span>Cost budget</span>
          <input
            type="number"
            min={0}
            max={1000}
            value={config.budget_policy.cost_usd ?? ""}
            onChange={(event) => onBudgetChange({ cost_usd: event.target.value === "" ? null : Number(event.target.value) })}
          />
        </label>
        <label className="agent-inline-toggle advanced-inline">
          <input type="checkbox" checked={config.compare_enabled} onChange={(event) => onConfigChange({ compare_enabled: event.target.checked })} />
          <span>Compare</span>
        </label>
      </div>
      <div className="advanced-check-grid">
        <fieldset>
          <legend>Validation</legend>
          {ADVANCED_VALIDATION_RULES.map((rule) => (
            <label key={rule} className="agent-inline-toggle">
              <input
                type="checkbox"
                checked={config.validation_rules.includes(rule)}
                onChange={(event) => onConfigChange({ validation_rules: toggleList(config.validation_rules, rule, event.target.checked) })}
              />
              <span>{rule}</span>
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>Stop</legend>
          {ADVANCED_STOP_CONDITIONS.map((condition) => (
            <label key={condition} className="agent-inline-toggle">
              <input
                type="checkbox"
                checked={config.stop_conditions.includes(condition)}
                onChange={(event) => onConfigChange({ stop_conditions: toggleList(config.stop_conditions, condition, event.target.checked) })}
              />
              <span>{condition.replace(/_/g, " ")}</span>
            </label>
          ))}
        </fieldset>
      </div>
      {validation.state === "failure" && validation.error && (
        <p className="advanced-validation-message" role="alert">
          {validation.error.field}: allowed {validation.error.allowed}
        </p>
      )}
    </details>
  );
}

function parseSourceScope(value: string): Record<string, unknown> {
  const ids = value.split(",").map((item) => item.trim()).filter(Boolean);
  if (ids.length > 0) return { kind: "source-ids", source_ids: ids };
  return { kind: "all-project" };
}

function advancedStateLabel(validation: AdvancedValidationResult): string {
  if (validation.state === "loading") return "Loading";
  if (validation.state === "failure") return "Failure";
  if (validation.state === "permission-denied") return "Permission denied";
  if (validation.state === "empty") return "Empty";
  return "Ready";
}

function toggleList<T extends string>(items: T[], item: T, enabled: boolean): T[] {
  if (enabled) return items.includes(item) ? items : [...items, item];
  return items.filter((current) => current !== item);
}

function previewMarkdown(markdown?: string): string {
  if (!markdown) return "Artifact preview unavailable.";
  return markdown.length > 1600 ? `${markdown.slice(0, 1600)}\n...` : markdown;
}

function riskBadgeClass(risk: string): string {
  if (risk === "high") return "risk-badge risk-high";
  if (risk === "medium") return "risk-badge risk-medium";
  return "risk-badge risk-low";
}
