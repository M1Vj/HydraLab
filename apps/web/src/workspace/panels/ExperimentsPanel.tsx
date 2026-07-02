import { useCallback, useEffect, useMemo, useState } from "react";
import { FlaskConical, LockKeyhole, Pause, Play, RotateCcw, ShieldCheck, XCircle } from "lucide-react";
import { HydraApiError } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";
import {
  approveRun,
  buildCreateRunPayload,
  cancelRun,
  canApprove,
  canPauseOrCancel,
  canRollback,
  canStart,
  createRun,
  derivePanelState,
  enableExecution,
  fetchBackends,
  fetchExecutionSetting,
  fetchRuns,
  pauseRun,
  rollbackRun,
  runControlsEnabled,
  selectableBackends,
  startRun,
  statusLabel,
  type ComputeBackend,
  type ExecutionSetting,
  type ExperimentRun,
} from "./experimentsController";

const PROJECT_ID = "default";
const SAMPLE_ARGV = ["python3", "-c", "print('##HYDRA_METRIC {\"accuracy\": 0.5}')"];

export function ExperimentsPanel({ announce }: PanelComponentProps) {
  const [setting, setSetting] = useState<ExecutionSetting | null>(null);
  const [backends, setBackends] = useState<ComputeBackend[]>([]);
  const [runs, setRuns] = useState<ExperimentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextSetting, nextBackends, nextRuns] = await Promise.all([
        fetchExecutionSetting(PROJECT_ID),
        fetchBackends(),
        fetchRuns(PROJECT_ID),
      ]);
      setSetting(nextSetting);
      setBackends(nextBackends);
      setRuns(nextRuns);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const panelState = useMemo(
    () =>
      derivePanelState({
        loading,
        error,
        executionEnabled: Boolean(setting?.execution_enabled),
        runCount: runs.length,
      }),
    [loading, error, setting, runs.length],
  );

  const guard = useCallback(
    async (action: () => Promise<unknown>, message: string) => {
      setBusy(true);
      try {
        await action();
        announce(message);
        await load();
      } catch (err) {
        setError(err as Error);
      } finally {
        setBusy(false);
      }
    },
    [announce, load],
  );

  const onEnable = () =>
    guard(async () => {
      await enableExecution(PROJECT_ID);
    }, "Execution enabled for this project");

  const onPropose = () => {
    const backend = selectableBackends(backends)[0];
    if (!backend) return;
    return guard(async () => {
      await createRun(
        buildCreateRunPayload({ projectId: PROJECT_ID, backendId: backend.id, label: "sandbox-check", argv: SAMPLE_ARGV }),
      );
    }, "Experiment proposed; awaiting your approval");
  };

  if (panelState === "loading") {
    return (
      <PanelScaffold title="Experiments">
        <LoadingState title="Loading experiments" />
      </PanelScaffold>
    );
  }

  if (panelState === "failure") {
    return (
      <PanelScaffold title="Experiments">
        <FailureState error={error ?? new HydraApiError({ kind: "http", message: "Unknown error" })} onRetry={load} />
      </PanelScaffold>
    );
  }

  if (panelState === "permission-denied") {
    return (
      <PanelScaffold title="Experiments">
        <div className="panel-state permission-denied" role="status">
          <LockKeyhole size={18} aria-hidden />
          <strong>Execution is not enabled</strong>
          <span>
            Running experiments executes real, user-authored code inside a sandbox. Enable execution for this project to
            unlock run controls. Every run stays gated behind an explicit approval and a pre-run checkpoint.
          </span>
          <button type="button" onClick={onEnable} disabled={busy}>
            <ShieldCheck size={14} aria-hidden /> Enable execution
          </button>
        </div>
      </PanelScaffold>
    );
  }

  return (
    <PanelScaffold title="Experiments">
      <section className="experiments-panel" aria-label="Experiments">
        <header className="experiments-toolbar">
          <div>
            <strong>Compute &amp; experiments</strong>
            <span className="muted">
              {selectableBackends(backends).length} backend(s) available · execution enabled
            </span>
          </div>
          <button type="button" onClick={onPropose} disabled={busy || !runControlsEnabled(setting)}>
            <FlaskConical size={14} aria-hidden /> Propose sandbox run
          </button>
        </header>

        {panelState === "empty" ? (
          <EmptyState
            title="No experiment runs yet"
            message="Propose a sandboxed run to get started. It will wait for your approval before any code executes."
            action="Propose sandbox run"
            onAction={onPropose}
          />
        ) : (
          <ul className="experiments-list">
            {runs.map((run) => (
              <li key={run.id} className={`experiment-row status-${run.status.replace(/[:]/g, "-")}`}>
                <div className="experiment-meta">
                  <span className="experiment-label">{run.label || run.id.slice(0, 8)}</span>
                  <span className="experiment-status" data-status={run.status}>
                    {statusLabel(run.status)}
                  </span>
                  {run.review_item_id && <span className="badge warn">Review Inbox</span>}
                  {run.enforcement === "best_effort" && <span className="badge warn">best-effort isolation</span>}
                </div>
                {run.reason && <p className="experiment-reason">{run.reason}</p>}
                <div className="experiment-actions">
                  <button
                    type="button"
                    onClick={() => guard(() => approveRun(run.id), "Run approved")}
                    disabled={busy || !canApprove(run)}
                  >
                    <ShieldCheck size={13} aria-hidden /> Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => guard(() => startRun(run.id), "Run started")}
                    disabled={busy || !canStart(run, setting)}
                  >
                    <Play size={13} aria-hidden /> Start
                  </button>
                  <button
                    type="button"
                    onClick={() => guard(() => pauseRun(run.id), "Run paused")}
                    disabled={busy || !canPauseOrCancel(run)}
                  >
                    <Pause size={13} aria-hidden /> Pause
                  </button>
                  <button
                    type="button"
                    onClick={() => guard(() => cancelRun(run.id), "Run cancelled")}
                    disabled={busy || !canPauseOrCancel(run)}
                  >
                    <XCircle size={13} aria-hidden /> Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => guard(() => rollbackRun(run.id), "Rolled back to pre-run checkpoint")}
                    disabled={busy || !canRollback(run)}
                  >
                    <RotateCcw size={13} aria-hidden /> Rollback
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </PanelScaffold>
  );
}
