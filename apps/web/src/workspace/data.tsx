import { createContext, useContext, useMemo } from "react";
import type React from "react";
import {
  api,
  type ActivityEventRecord,
  type ProjectObjectsResponse,
  type ProjectTreeResponse,
  type ReviewItem,
  type SettingsResponse,
} from "../lib/api";
import { useApiResource, type ResourceState } from "./useApiResource";

type WorkspaceDataContextValue = {
  projectId: string;
  objects: ResourceState<ProjectObjectsResponse> & { reload: () => void };
  tree: ResourceState<ProjectTreeResponse> & { reload: () => void };
  review: ResourceState<{ items: ReviewItem[]; counts: { pending: number; review_items: number; recovery: number } }> & { reload: () => void };
  events: ResourceState<{ events: ActivityEventRecord[] }> & { reload: () => void };
  settings: ResourceState<SettingsResponse> & { reload: () => void };
  refreshAll: () => void;
};

const WorkspaceDataContext = createContext<WorkspaceDataContextValue | null>(null);

export function WorkspaceDataProvider({ children, projectId }: { children: React.ReactNode; projectId: string }) {
  const objects = useApiResource(() => api.get<ProjectObjectsResponse>(`/api/project/objects?project_id=${encodeURIComponent(projectId)}`), [projectId]);
  const tree = useApiResource(() => api.get<ProjectTreeResponse>("/api/project/tree"), [projectId]);
  const review = useApiResource(
    () => api.get<{ items: ReviewItem[]; counts: { pending: number; review_items: number; recovery: number } }>(`/api/review-inbox?project_id=${encodeURIComponent(projectId)}`),
    [projectId],
  );
  const events = useApiResource(() => api.get<{ events: ActivityEventRecord[] }>("/api/events"), [projectId]);
  const settings = useApiResource(() => api.get<SettingsResponse>("/api/settings"), [projectId]);

  const value = useMemo(
    () => ({
      projectId,
      objects,
      tree,
      review,
      events,
      settings,
      refreshAll: () => {
        objects.reload();
        tree.reload();
        review.reload();
        events.reload();
        settings.reload();
      },
    }),
    [projectId, objects.status, tree.status, review.status, events.status, settings.status],
  );

  return <WorkspaceDataContext.Provider value={value}>{children}</WorkspaceDataContext.Provider>;
}

export function useWorkspaceData() {
  const value = useContext(WorkspaceDataContext);
  if (!value) throw new Error("useWorkspaceData must be used inside WorkspaceDataProvider");
  return value;
}
