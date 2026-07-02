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
