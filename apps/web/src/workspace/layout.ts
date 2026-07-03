import type { IJsonModel, IJsonTabNode } from "flexlayout-react";
import { defaultWorkbenchLayout, tab, tabStableKey, type PanelConfig, type PanelId, type PanelLocation, panelChrome } from "./panelRegistry";

export type WorkspaceLayoutState = {
  layouts: Record<string, IJsonModel>;
  activeLayout: string;
};

export const WORKSPACE_LAYOUT_VERSION = 1;

export type PersistedWorkspaceState = {
  version: number;
  projects: Record<string, WorkspaceLayoutState>;
};

export function defaultLayoutState(): WorkspaceLayoutState {
  return { activeLayout: "Default", layouts: { Default: defaultWorkbenchLayout() } };
}

export function safeParseWorkspaceState(raw: string | null): PersistedWorkspaceState {
  if (!raw) return { version: WORKSPACE_LAYOUT_VERSION, projects: {} };
  try {
    const parsed = JSON.parse(raw) as Partial<PersistedWorkspaceState>;
    return migrateWorkspaceState(parsed);
  } catch {
    return { version: WORKSPACE_LAYOUT_VERSION, projects: {} };
  }
}

export function migrateWorkspaceState(input: Partial<PersistedWorkspaceState>): PersistedWorkspaceState {
  if (!input || typeof input !== "object") return { version: WORKSPACE_LAYOUT_VERSION, projects: {} };
  const projects = typeof input.projects === "object" && input.projects ? input.projects : {};
  return {
    version: WORKSPACE_LAYOUT_VERSION,
    projects: Object.fromEntries(
      Object.entries(projects).map(([projectKey, state]) => {
        const activeLayout = typeof state.activeLayout === "string" ? state.activeLayout : "Default";
        const layouts = state.layouts && typeof state.layouts === "object" ? state.layouts : {};
        return [projectKey, { activeLayout, layouts: Object.keys(layouts).length ? layouts : { Default: defaultWorkbenchLayout() } }];
      }),
    ),
  };
}

export function layoutForProject(state: PersistedWorkspaceState, projectKey: string): WorkspaceLayoutState {
  return state.projects[projectKey] ?? defaultLayoutState();
}

export function activeJsonLayout(state: WorkspaceLayoutState): IJsonModel {
  return state.layouts[state.activeLayout] ?? state.layouts.Default ?? defaultWorkbenchLayout();
}

export function saveLayoutForProject(
  state: PersistedWorkspaceState,
  projectKey: string,
  layoutName: string,
  layout: IJsonModel,
): PersistedWorkspaceState {
  const project = layoutForProject(state, projectKey);
  return {
    version: WORKSPACE_LAYOUT_VERSION,
    projects: {
      ...state.projects,
      [projectKey]: {
        activeLayout: layoutName,
        layouts: { ...project.layouts, [layoutName]: layout },
      },
    },
  };
}

export function openPanelInLayout(layout: IJsonModel, panelId: PanelId, config: PanelConfig = {}): IJsonModel {
  const targetKey = tabStableKey(panelId, config);
  const cloned = structuredClone(layout) as IJsonModel;
  const existing = findTab(cloned, targetKey);
  if (existing) {
    markSelected(existing.parent, existing.index);
    return cloned;
  }

  const nextTab = tab(panelId, config);
  const location = panelChrome[panelId].defaultLocation;
  const target = findTargetContainer(cloned, location);
  target.children.push(nextTab);
  markSelected(target, target.children.length - 1);
  return cloned;
}

export function removeActiveTabFromLayout(layout: IJsonModel): IJsonModel {
  const cloned = structuredClone(layout) as IJsonModel;
  const containers = collectTabContainers(cloned);
  for (const container of containers) {
    const selected = typeof container.selected === "number" ? container.selected : 0;
    if (container.children?.[selected]) {
      container.children.splice(selected, 1);
      markSelected(container, Math.max(0, selected - 1));
      break;
    }
  }
  return cloned;
}

export function switchLayout(state: WorkspaceLayoutState, name: string): WorkspaceLayoutState {
  return state.layouts[name] ? { ...state, activeLayout: name } : state;
}

export function resetLayout(state: WorkspaceLayoutState): WorkspaceLayoutState {
  return { ...state, activeLayout: "Default", layouts: { ...state.layouts, Default: defaultWorkbenchLayout() } };
}

export function saveLayoutAs(state: WorkspaceLayoutState, name: string, layout: IJsonModel): WorkspaceLayoutState {
  const cleanName = name.trim();
  if (!cleanName) return state;
  return { activeLayout: cleanName, layouts: { ...state.layouts, [cleanName]: layout } };
}

type TabContainer = { children: IJsonTabNode[]; selected?: number; id?: string; type?: string };

function markSelected(container: TabContainer, index: number) {
  container.selected = Math.max(0, Math.min(index, Math.max(0, container.children.length - 1)));
}

function findTargetContainer(layout: IJsonModel, location: PanelLocation): TabContainer {
  if (location === "border-left") return findBorder(layout, "left");
  if (location === "border-bottom") return findBorder(layout, "bottom");
  if (location === "border-right") return findTabset(layout, "right_main");
  return findTabset(layout, "center_main");
}

function findBorder(layout: IJsonModel, location: "left" | "right" | "top" | "bottom"): TabContainer {
  const found = layout.borders?.find((border) => border.location === location);
  if (!found) throw new Error(`Missing ${location} border`);
  return found as TabContainer;
}

function findTabset(layout: IJsonModel, id: string): TabContainer {
  const found = collectTabContainers(layout).find((container) => container.id === id);
  if (!found) throw new Error(`Missing tabset ${id}`);
  return found;
}

function findTab(layout: IJsonModel, tabId: string): { parent: TabContainer; index: number } | null {
  for (const container of collectTabContainers(layout)) {
    const index = container.children.findIndex((child) => child.id === tabId);
    if (index !== -1) return { parent: container, index };
  }
  return null;
}

function collectTabContainers(layout: IJsonModel): TabContainer[] {
  const containers: TabContainer[] = [];
  for (const border of layout.borders ?? []) {
    containers.push(border as TabContainer);
  }
  visit(layout.layout);
  return containers;

  function visit(node: unknown) {
    if (!node || typeof node !== "object") return;
    const item = node as { type?: string; children?: unknown[] };
    if (item.type === "tabset" && Array.isArray(item.children)) containers.push(item as TabContainer);
    for (const child of item.children ?? []) visit(child);
  }
}
