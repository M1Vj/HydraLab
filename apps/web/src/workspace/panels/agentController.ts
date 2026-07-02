import {
  api,
  type AgentApproval,
  type AgentRunTrace,
  type ApiClient,
  type AssistantModes,
  type SkillInfo,
} from "../../lib/api";

/** The exactly three canonical Agent Access Mode ids (DEC-5). */
export const AGENT_ACCESS_MODES = ["passive", "copilot", "full_access"] as const;
export type AgentAccessMode = (typeof AGENT_ACCESS_MODES)[number];

export const MODE_LABELS: Record<AgentAccessMode, string> = {
  passive: "Passive (Suggest-only)",
  copilot: "Co-pilot (Approve-to-apply)",
  full_access: "Full Access (YOLO)",
};

export function modeLabel(id: string): string {
  return MODE_LABELS[id as AgentAccessMode] ?? id;
}

/** A mode is selectable only if the backend marks it enabled for this project. */
export function isModeSelectable(modes: AssistantModes, id: string): boolean {
  return Boolean(modes.modes.find((mode) => mode.id === id)?.enabled);
}

export function fetchModes(projectId: string, client: ApiClient = api): Promise<AssistantModes> {
  return client.get<AssistantModes>(`/api/assistant/modes?project_id=${encodeURIComponent(projectId)}`);
}

export function setMode(mode: string, projectId: string, client: ApiClient = api): Promise<{ default_mode: string; full_access_enabled: boolean }> {
  return client.post("/api/assistant/mode", { mode, project_id: projectId });
}

export function setFullAccess(enabled: boolean, projectId: string, client: ApiClient = api): Promise<{ full_access_enabled: boolean; default_mode: string }> {
  return client.post("/api/assistant/full-access", { enabled, project_id: projectId });
}

export function toggleSkill(skillId: string, enabled: boolean, client: ApiClient = api): Promise<SkillInfo> {
  return client.post<SkillInfo>(`/api/skills/${encodeURIComponent(skillId)}/enabled`, { enabled });
}

export function editSkill(skillId: string, text: string, client: ApiClient = api): Promise<{ skill: SkillInfo; validation_error: string | null }> {
  return client.put(`/api/skills/${encodeURIComponent(skillId)}`, { text });
}

export function restoreSkillDefault(skillId: string, client: ApiClient = api): Promise<SkillInfo> {
  return client.post<SkillInfo>(`/api/skills/${encodeURIComponent(skillId)}/restore`, {});
}

export function fetchApprovals(projectId: string, client: ApiClient = api): Promise<AgentApproval[]> {
  return client
    .get<{ approvals: AgentApproval[] }>(`/api/agent/approvals?project_id=${encodeURIComponent(projectId)}`)
    .then((payload) => payload.approvals);
}

export function resolveApproval(approvalId: string, decision: "approved" | "rejected", client: ApiClient = api): Promise<{ applied: boolean; status: string }> {
  return client.post(`/api/agent/approvals/${encodeURIComponent(approvalId)}/resolve`, { decision });
}

export function fetchRunTrace(runId: string, client: ApiClient = api): Promise<AgentRunTrace> {
  return client.get<AgentRunTrace>(`/api/agent/runs/${encodeURIComponent(runId)}`);
}

export function pauseRun(runId: string, paused: boolean, client: ApiClient = api): Promise<{ id: string; status: string; paused: boolean }> {
  return client.post(`/api/agent/runs/${encodeURIComponent(runId)}/pause?paused=${paused}`, {});
}

/** A step whose outcome traces to untrusted content or a denied capability is flagged. */
export function isFlaggedStep(step: { denied_capability?: string | null; trust_origin: string }): boolean {
  return Boolean(step.denied_capability) || step.trust_origin === "untrusted-external";
}
