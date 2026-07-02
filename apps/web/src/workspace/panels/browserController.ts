import { api, type ApiClient } from "../../lib/api";

export type BrowserMode = { id: "passive" | "copilot"; label: string; enabled: boolean };
export type BrowserPermissionState = "ask" | "allow_for_task" | "always_allow_host" | "blocked";
export type BrowserActionDescriptor = {
  name: string;
  description?: string;
  verb: string;
  host: string;
  read_only?: boolean;
};

export type BrowserActionLogEntry = {
  id: string;
  project_id: string;
  action: string;
  host: string;
  mode: "copilot" | string;
  approval_result: string;
  timestamp: string;
  target_url?: string;
  task_group_id?: string | null;
};

export type BrowserTab = {
  id: string;
  title: string;
  url: string;
  task_group_id?: string | null;
  task_group_label?: string | null;
};

export type BrowserTabGroup = {
  id: string;
  label: string;
  tabs: BrowserTab[];
};

export type BrowserActionLogView = {
  state: "empty" | "loading" | "failure" | "permission-denied" | "ready";
  message: string;
};

export type BrowserRunRecord = {
  id: string;
  project_id: string;
  recipe: "autonomous-browser-research" | string;
  mode: "passive" | "copilot" | "full_access" | string;
  status: "queued" | "running" | "paused" | "succeeded" | "failed" | "cancelled" | "blocked" | string;
  paused: boolean;
  tokens_used: number;
  created_at: number;
  artifacts: Array<Record<string, unknown>>;
};

export type BrowserRunStartRequest = {
  project_id: string;
  task_id: string;
  task_label: string;
  start_urls: string[];
};

export type BrowserRunStartResponse = {
  run: BrowserRunRecord;
  state: string;
  host_prompt?: { host: string; choices?: string[] } | null;
  budget_prompt?: string[] | null;
  rate_limit_state?: string | null;
};

export type BrowserRunView = {
  state: "empty" | "loading" | "failure" | "permission-denied" | "ready";
  message: string;
};

export const BROWSER_MODES: BrowserMode[] = [
  { id: "passive", label: "Passive", enabled: true },
  { id: "copilot", label: "Co-pilot", enabled: true },
];

export function browserActionLogState(input: {
  loading: boolean;
  error: Error | null;
  permissionDenied: boolean;
  actions: BrowserActionLogEntry[];
}): BrowserActionLogView {
  if (input.loading) return { state: "loading", message: "Loading browser actions." };
  if (input.permissionDenied) return { state: "permission-denied", message: "Browser action log is not available for this project." };
  if (input.error) return { state: "failure", message: input.error.message };
  if (input.actions.length === 0) return { state: "empty", message: "No approved browser actions have run yet." };
  return { state: "ready", message: "Browser action log ready." };
}

export function browserRunState(input: {
  loading: boolean;
  error: Error | null;
  permissionDenied: boolean;
  runs: BrowserRunRecord[];
}): BrowserRunView {
  if (input.loading) return { state: "loading", message: "Loading browser runs." };
  if (input.permissionDenied) return { state: "permission-denied", message: "Autonomous browser runs are not available for this project." };
  if (input.error) return { state: "failure", message: input.error.message };
  if (input.runs.length === 0) return { state: "empty", message: "No autonomous browser research runs yet." };
  return { state: "ready", message: "Autonomous browser runs ready." };
}

export function groupBrowserTabs(tabs: BrowserTab[]): BrowserTabGroup[] {
  const groups = new Map<string, BrowserTabGroup>();
  for (const tab of tabs) {
    const id = tab.task_group_id || "ungrouped";
    const label = tab.task_group_label || "Ungrouped";
    if (!groups.has(id)) groups.set(id, { id, label, tabs: [] });
    groups.get(id)!.tabs.push(tab);
  }
  return [...groups.values()];
}

export function listBrowserActions(host: string, client: ApiClient = api): Promise<{ actions: BrowserActionDescriptor[] }> {
  return client.get<{ actions: BrowserActionDescriptor[] }>(`/api/browser/actions?host=${encodeURIComponent(host)}`);
}

export function listBrowserActionLog(projectId: string, client: ApiClient = api): Promise<{ actions: BrowserActionLogEntry[] }> {
  return client.get<{ actions: BrowserActionLogEntry[] }>(`/api/browser/action-log?project_id=${encodeURIComponent(projectId)}`);
}

export function listAutonomousBrowserRuns(projectId: string, client: ApiClient = api): Promise<{ runs: BrowserRunRecord[] }> {
  return client.get<{ runs: BrowserRunRecord[] }>(`/api/browser/autonomous-runs?project_id=${encodeURIComponent(projectId)}`);
}

export function startAutonomousBrowserRun(
  request: BrowserRunStartRequest,
  client: ApiClient = api,
): Promise<BrowserRunStartResponse> {
  return client.post<BrowserRunStartResponse>("/api/browser/autonomous-runs", request);
}

export function stopAutonomousBrowserRun(runId: string, client: ApiClient = api): Promise<{ run: BrowserRunRecord }> {
  return client.post<{ run: BrowserRunRecord }>(`/api/browser/autonomous-runs/${encodeURIComponent(runId)}/cancel`, {});
}

export function setBrowserHostPermission(
  projectId: string,
  host: string,
  state: BrowserPermissionState,
  client: ApiClient = api,
): Promise<{ permission: { project_id: string; host: string; state: BrowserPermissionState } }> {
  return client.post<{ permission: { project_id: string; host: string; state: BrowserPermissionState } }>("/api/browser/permissions", {
    project_id: projectId,
    host,
    state,
  });
}
