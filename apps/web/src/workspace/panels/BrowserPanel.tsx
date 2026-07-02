import { useEffect, useMemo, useState } from "react";
import { Play, RefreshCcw, ShieldCheck, Square } from "lucide-react";
import { api, type BrowserEventRecord } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";
import {
  BROWSER_MODES,
  browserActionLogState,
  browserRunState,
  groupBrowserTabs,
  listAutonomousBrowserRuns,
  listBrowserActionLog,
  setBrowserHostPermission,
  startAutonomousBrowserRun,
  stopAutonomousBrowserRun,
  type BrowserActionLogEntry,
  type BrowserPermissionState,
  type BrowserRunRecord,
  type BrowserTab,
} from "./browserController";

const PROJECT_ID = "default";
const PERMISSION_STATES: BrowserPermissionState[] = ["ask", "allow_for_task", "always_allow_host", "blocked"];

export function BrowserPanel({ config, announce }: PanelComponentProps) {
  const initialUrl = typeof config?.url === "string" ? config.url : "https://arxiv.org/abs/1706.03762";
  const [mode, setMode] = useState<"passive" | "copilot">("passive");
  const [host, setHost] = useState(() => safeHost(initialUrl));
  const [permission, setPermission] = useState<BrowserPermissionState>("ask");
  const [events, setEvents] = useState<BrowserEventRecord[]>([]);
  const [actions, setActions] = useState<BrowserActionLogEntry[]>([]);
  const [runs, setRuns] = useState<BrowserRunRecord[]>([]);
  const [runUrl, setRunUrl] = useState(initialUrl);
  const [hostPrompt, setHostPrompt] = useState<{ host: string; choices?: string[] } | null>(null);
  const [budgetPrompt, setBudgetPrompt] = useState<string[] | null>(null);
  const [rateLimitState, setRateLimitState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [runBusy, setRunBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  useEffect(() => {
    void load();
  }, []);

  const tabs: BrowserTab[] = useMemo(
    () =>
      events.map((event) => ({
        id: event.id,
        title: event.title || event.url,
        url: event.url,
        task_group_id: stringFromMetadata(event.detected_metadata?.task_group_id, "current"),
        task_group_label: stringFromMetadata(event.detected_metadata?.task_group_label, "Current research task"),
      })),
    [events],
  );
  const tabGroups = useMemo(() => groupBrowserTabs(tabs), [tabs]);
  const logView = browserActionLogState({ loading, error, permissionDenied, actions });
  const runView = browserRunState({ loading, error, permissionDenied, runs });
  const activeRun = runs.find((run) => ["queued", "running", "paused", "blocked"].includes(run.status)) ?? runs[0] ?? null;

  async function load() {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      const [ledger, log, runList] = await Promise.all([
        api.get<{ events: BrowserEventRecord[] }>(`/api/browser/ledger?project_id=${PROJECT_ID}`),
        listBrowserActionLog(PROJECT_ID),
        listAutonomousBrowserRuns(PROJECT_ID),
      ]);
      setEvents(ledger.events);
      setActions(log.actions);
      setRuns(runList.runs);
    } catch (caught) {
      const err = caught instanceof Error ? caught : new Error(String(caught));
      setError(err);
      setPermissionDenied("kind" in err && (err as { kind?: string }).kind === "permission-denied");
    } finally {
      setLoading(false);
    }
  }

  async function updatePermission(next: BrowserPermissionState) {
    setPermission(next);
    await setBrowserHostPermission(PROJECT_ID, host, next);
    announce(`Browser host permission set to ${next}`);
  }

  async function startRun() {
    setRunBusy(true);
    setError(null);
    setHostPrompt(null);
    setBudgetPrompt(null);
    setRateLimitState(null);
    try {
      const response = await startAutonomousBrowserRun({
        project_id: PROJECT_ID,
        task_id: "browser-research",
        task_label: "Browser research",
        start_urls: [runUrl],
      });
      setRuns((current) => [response.run, ...current.filter((run) => run.id !== response.run.id)]);
      setHostPrompt(response.host_prompt ?? null);
      setBudgetPrompt(response.budget_prompt ?? null);
      setRateLimitState(response.rate_limit_state ?? null);
      announce(`Browser run ${response.run.status}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setRunBusy(false);
    }
  }

  async function stopRun(runId: string) {
    setRunBusy(true);
    try {
      const response = await stopAutonomousBrowserRun(runId);
      setRuns((current) => [response.run, ...current.filter((run) => run.id !== response.run.id)]);
      announce("Browser run cancelled");
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setRunBusy(false);
    }
  }

  if (loading) return <LoadingState title="Loading browser" />;
  if (error && !permissionDenied) return <FailureState error={error} onRetry={load} />;

  return (
    <PanelScaffold title="Browser">
      <header className="panel-toolbar browser-toolbar">
        <div className="mode-segment" aria-label="Browser Agent Access Mode">
          {BROWSER_MODES.map((choice) => (
            <button key={choice.id} className={mode === choice.id ? "active" : ""} aria-pressed={mode === choice.id} onClick={() => setMode(choice.id)}>
              {choice.label}
            </button>
          ))}
        </div>
        <button onClick={() => void load()} aria-label="Refresh browser panel">
          <RefreshCcw size={14} /> Refresh
        </button>
      </header>

      <section className="browser-run-panel" aria-label="Autonomous browser research run">
        <label>
          URL
          <input value={runUrl} onChange={(event) => setRunUrl(event.target.value)} aria-label="Autonomous browser run URL" />
        </label>
        <button onClick={() => void startRun()} disabled={runBusy || !runUrl.trim()} aria-label="Start autonomous browser research">
          <Play size={14} /> Run
        </button>
        <button
          onClick={() => activeRun && void stopRun(activeRun.id)}
          disabled={runBusy || !activeRun || ["succeeded", "failed", "cancelled"].includes(activeRun.status)}
          aria-label="Stop autonomous browser research"
        >
          <Square size={14} /> Stop
        </button>
        {activeRun && (
          <span className={`status-pill ${activeRun.status}`}>
            {activeRun.recipe} / {activeRun.mode} / {activeRun.status}
          </span>
        )}
      </section>

      {(hostPrompt || budgetPrompt || rateLimitState) && (
        <section className="browser-run-state" aria-label="Browser run state">
          {hostPrompt && (
            <div className="object-card">
              <strong>{hostPrompt.host}</strong>
              <div className="row-actions">
                {(hostPrompt.choices ?? []).map((choice) => (
                  <button
                    key={choice}
                    onClick={() => {
                      const next = choice === "Always allow this host" ? "always_allow_host" : choice === "Decline/block this host" ? "blocked" : "allow_for_task";
                      void updatePermission(next);
                    }}
                  >
                    {choice}
                  </button>
                ))}
              </div>
            </div>
          )}
          {budgetPrompt && <div className="panel-state permission-denied">{budgetPrompt.join(" / ")}</div>}
          {rateLimitState && <div className="panel-state permission-denied">{rateLimitState}</div>}
        </section>
      )}

      <section className="browser-permission-panel" aria-label="Per-host browser permission">
        <label>
          Host
          <input value={host} onChange={(event) => setHost(event.target.value)} aria-label="Browser host" />
        </label>
        <label>
          Permission
          <select value={permission} onChange={(event) => void updatePermission(event.target.value as BrowserPermissionState)} aria-label="Host permission">
            {PERMISSION_STATES.map((state) => (
              <option key={state} value={state}>
                {state}
              </option>
            ))}
          </select>
        </label>
        <span className={`status-pill ${permission}`}>
          <ShieldCheck size={12} aria-hidden /> {permission}
        </span>
      </section>

      <section aria-label="Browser task groups" className="browser-task-groups">
        {tabGroups.length === 0 ? (
          <EmptyState title="No task tabs" message="Browser tabs grouped by research task will appear here." />
        ) : (
          tabGroups.map((group) => (
            <article className="object-card" key={group.id}>
              <strong>{group.label}</strong>
              <small>{group.tabs.length} tab(s)</small>
              {group.tabs.map((tab) => (
                <span key={tab.id}>{tab.title}</span>
              ))}
            </article>
          ))
        )}
      </section>

      <section aria-label="Browser action log" className="browser-action-log">
        {logView.state === "empty" && <EmptyState title="No browser actions" message={logView.message} />}
        {logView.state === "permission-denied" && <div className="panel-state permission-denied" role="alert">{logView.message}</div>}
        {logView.state === "failure" && error && <FailureState error={error} onRetry={load} />}
        {logView.state === "ready" && (
          <div className="object-list">
            {actions.map((entry) => (
              <article className="object-card" key={entry.id}>
                <strong>{entry.action}</strong>
                <span>{entry.host}</span>
                <small>
                  {entry.mode} / {entry.approval_result} / {entry.timestamp}
                </small>
              </article>
            ))}
          </div>
        )}
      </section>

      <section aria-label="Autonomous browser run log" className="browser-action-log">
        {runView.state === "empty" && <EmptyState title="No browser runs" message={runView.message} />}
        {runView.state === "permission-denied" && <div className="panel-state permission-denied" role="alert">{runView.message}</div>}
        {runView.state === "failure" && error && <FailureState error={error} onRetry={load} />}
        {runView.state === "ready" && (
          <div className="object-list">
            {runs.map((entry) => (
              <article className="object-card" key={entry.id}>
                <strong>{entry.status}</strong>
                <span>{entry.recipe}</span>
                <small>
                  {entry.mode} / {entry.tokens_used} tokens
                </small>
              </article>
            ))}
          </div>
        )}
      </section>
    </PanelScaffold>
  );
}

function safeHost(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

function stringFromMetadata(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}
