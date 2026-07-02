import { useEffect, useMemo, useState } from "react";
import { Boxes, CheckCircle2, CircleDashed, FileText, ListRestart, Play, RefreshCcw, Save, SkipForward, XCircle } from "lucide-react";
import type { AgentRunArtifact, AgentTraceStep, OrchestratorRunResponse, OrchestratorStage } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { FailureState, LoadingState, PanelScaffold } from "./PanelState";
import {
  CANONICAL_STAGE_IDS,
  cancelAgentRun,
  defaultStageToggles,
  fetchOrchestratorStages,
  fetchRecipes,
  requestLiteratureReviewSave,
  resolveLiteratureReviewSave,
  stageStatus,
  startLiteratureReviewRun,
  startOrchestratorRun,
  summarizeRunState,
  toggleStage,
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

  async function loadStages() {
    setLoading(true);
    setError(null);
    try {
      const [loaded, loadedRecipes] = await Promise.all([fetchOrchestratorStages(), fetchRecipes()]);
      setStages(loaded);
      setRecipes(loadedRecipes);
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
    if (isLiteratureReview) {
      await startLiteratureRun();
      return;
    }
    await startRecipeRun();
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
      await cancelAgentRun(run.run.id);
      const next = { ...run, run: { ...run.run, status: "cancelled", state: "cancelled" } };
      setRun(next);
      announce("Run cancelled");
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

        <div className={`agent-run-banner ${run?.run.status ?? "idle"}`} role="status">
          <ListRestart size={15} aria-hidden />
          <strong>{banner}</strong>
          {run && <span>{run.run.mode} - {run.trace.steps.length} events</span>}
          {run && run.run.status === "running" && (
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

function parseSourceScope(value: string): Record<string, unknown> {
  const ids = value.split(",").map((item) => item.trim()).filter(Boolean);
  if (ids.length > 0) return { kind: "source-ids", source_ids: ids };
  return { kind: "all-project" };
}

function previewMarkdown(markdown?: string): string {
  if (!markdown) return "Artifact preview unavailable.";
  return markdown.length > 1600 ? `${markdown.slice(0, 1600)}\n...` : markdown;
}
