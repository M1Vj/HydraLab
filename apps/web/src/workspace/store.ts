import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { IJsonModel } from "flexlayout-react";
import {
  activeJsonLayout,
  defaultLayoutState,
  resetLayout,
  saveLayoutAs,
  saveLayoutForProject,
  switchLayout,
  type PersistedWorkspaceState,
  type WorkspaceLayoutState,
  WORKSPACE_LAYOUT_VERSION,
} from "./layout";

export type ActiveProject = {
  id: string;
  path: string;
  name: string;
};

export type RecentProject = ActiveProject & {
  lastOpenedAt: number;
  exists?: boolean;
};

type WorkspaceStore = {
  projects: PersistedWorkspaceState["projects"];
  activeProject: ActiveProject | null;
  recentProjects: RecentProject[];
  setActiveProject: (project: ActiveProject | null) => void;
  removeRecentProject: (path: string) => void;
  activeLayoutState: () => WorkspaceLayoutState;
  activeLayoutJson: () => IJsonModel;
  saveActiveLayout: (layout: IJsonModel) => void;
  resetActiveLayout: () => void;
  saveActiveLayoutAs: (name: string, layout: IJsonModel) => void;
  switchActiveLayout: (name: string) => void;
};

export const useWorkspaceStore = create<WorkspaceStore>()(
  persist(
    (set, get) => ({
      projects: {},
      activeProject: null,
      recentProjects: [],
      setActiveProject: (project) =>
        set((state) => {
          if (!project) return { activeProject: null };
          const existing = state.projects[project.path] ?? defaultLayoutState();
          const recents = [
            { ...project, lastOpenedAt: Date.now(), exists: true },
            ...state.recentProjects.filter((recent) => recent.path !== project.path),
          ].slice(0, 10);
          return {
            activeProject: project,
            projects: { ...state.projects, [project.path]: existing },
            recentProjects: recents,
          };
        }),
      removeRecentProject: (path) => set((state) => ({ recentProjects: state.recentProjects.filter((recent) => recent.path !== path) })),
      activeLayoutState: () => {
        const active = get().activeProject;
        if (!active) return defaultLayoutState();
        return get().projects[active.path] ?? defaultLayoutState();
      },
      activeLayoutJson: () => activeJsonLayout(get().activeLayoutState()),
      saveActiveLayout: (layout) =>
        set((state) => {
          if (!state.activeProject) return state;
          const projectState = state.projects[state.activeProject.path] ?? defaultLayoutState();
          const next = saveLayoutForProject(
            { version: WORKSPACE_LAYOUT_VERSION, projects: state.projects },
            state.activeProject.path,
            projectState.activeLayout,
            layout,
          );
          return { projects: next.projects };
        }),
      resetActiveLayout: () =>
        set((state) => {
          if (!state.activeProject) return state;
          const current = state.projects[state.activeProject.path] ?? defaultLayoutState();
          return { projects: { ...state.projects, [state.activeProject.path]: resetLayout(current) } };
        }),
      saveActiveLayoutAs: (name, layout) =>
        set((state) => {
          if (!state.activeProject) return state;
          const current = state.projects[state.activeProject.path] ?? defaultLayoutState();
          return { projects: { ...state.projects, [state.activeProject.path]: saveLayoutAs(current, name, layout) } };
        }),
      switchActiveLayout: (name) =>
        set((state) => {
          if (!state.activeProject) return state;
          const current = state.projects[state.activeProject.path] ?? defaultLayoutState();
          return { projects: { ...state.projects, [state.activeProject.path]: switchLayout(current, name) } };
        }),
    }),
    {
      name: "hydralab-workspace",
      version: WORKSPACE_LAYOUT_VERSION,
      storage: createJSONStorage(() => localStorage),
      migrate: (persisted) => {
        const state = persisted as Partial<WorkspaceStore>;
        return {
          ...state,
          projects: state.projects ?? {},
          recentProjects: state.recentProjects ?? [],
          activeProject: state.activeProject ?? null,
        } as WorkspaceStore;
      },
      partialize: (state) => ({
        projects: state.projects,
        activeProject: state.activeProject,
        recentProjects: state.recentProjects,
      }),
    },
  ),
);
