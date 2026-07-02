import { useEffect, useMemo, useState } from "react";
import { Boxes, CheckCircle2, CircleDashed, ListRestart, Play, RefreshCcw, SkipForward } from "lucide-react";
import type { AgentRunArtifact, AgentTraceStep, OrchestratorRunResponse, OrchestratorStage } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { FailureState, LoadingState, PanelScaffold } from "./PanelState";
import {
  CANONICAL_STAGE_IDS,
  defaultStageToggles,
  fetchOrchestratorStages,
  stageStatus,
  startOrchestratorRun,
  summarizeRunState,
  toggleStage,
  type StageId,
  type StageToggles,
} from "./agentRunsController";

const PROJECT_ID = "default";

function statusIcon(status: string) {
  if (status === "completed") return <CheckCircle2 size={14} aria-hidden />;
  if (status === "skipped") return <SkipForward size={14} aria-hidden />;
  return <CircleDashed size={14} aria-hidden />;
}

export function AgentRunsPanel({ announce }: PanelComponentProps) {
  const [stages, setStages] = useState<OrchestratorStage[]>([]);
  const [toggles, setToggles] = useState<StageToggles>(() => defaultStageToggles());
  const [run, setRun] = useState<OrchestratorRunResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    void loadStages();
  }, []);

  async function loadStages() {
    setLoading(true);
    setError(null);
    try {
      const loaded = await fetchOrchestratorStages();
      setStages(loaded);
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
    setRunning(true);
    setError(null);
    try {
      const started = await startOrchestratorRun(PROJECT_ID, toggles);
      setRun(started);
      announce(`Run ${summarizeRunState(started.run.status, started.run.state).toLowerCase()}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setRunning(false);
    }
  }

  function onToggle(stage: StageId, enabled: boolean) {
    setToggles((current) => toggleStage(current, stage, enabled));
  }

  const steps = run?.trace.steps ?? [];
  const artifacts = run?.artifacts ?? [];
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
            <h2>Bounded run</h2>
            <p>One fixed Phase-2 stage pass</p>
          </div>
          <button type="button" className="primary-action compact" onClick={() => void startRun()} disabled={running}>
            {running ? <RefreshCcw size={14} aria-hidden /> : <Play size={14} aria-hidden />}
            {running ? "Running" : "Start"}
          </button>
        </header>

        <div className={`agent-run-banner ${run?.run.status ?? "idle"}`} role="status">
          <ListRestart size={15} aria-hidden />
          <strong>{banner}</strong>
          {run && <span>{run.run.mode} - {run.trace.steps.length} events</span>}
        </div>

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
        </section>
      </div>
    </PanelScaffold>
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
