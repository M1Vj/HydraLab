import {
  api,
  type ApiClient,
  type CollaborationAuth,
  type CollaborationInvite,
  type CollaborationPermission,
  type CollaborationRevokeResponse,
  type CollaborationSettings,
  type CollaboratorRecord,
  type SettingsResponse,
} from "../../lib/api";

type ProviderSetting = SettingsResponse["provider_settings"][number];

/** Mirrors backend RAW_SECRET_PREFIXES so raw keys can be flagged before hitting the API. */
export const RAW_SECRET_PREFIXES = ["sk-", "ai-", "ghp_", "github_pat_", "xoxb-", "xoxp-", "AKIA", "ASIA"] as const;

export function looksLikeRawSecret(value: string): boolean {
  const trimmed = value.trim();
  return trimmed.length > 0 && RAW_SECRET_PREFIXES.some((prefix) => trimmed.startsWith(prefix));
}

/** A secret is considered stored when the backend resolved a keychain/env reference for it. */
export function providerSecretStored(provider: Pick<ProviderSetting, "secret_ref" | "auth_status" | "resolved">): boolean {
  return Boolean(provider.resolved || (provider.secret_ref && provider.secret_ref.length > 0) || provider.auth_status === "ready");
}

/** Write-only: sends the raw secret to the keychain-only endpoint and returns the stored reference. */
export function saveProviderSecret(provider: string, secret: string, client: ApiClient = api): Promise<{ secret_ref: string }> {
  return client.post<{ secret_ref: string }>("/api/settings/provider/secret", { provider, secret });
}

/**
 * Persists provider model + config with a reference value only. The backend rejects raw
 * secrets here with a 400 (surfaced as a HydraApiError), so never pass a raw key.
 */
export function saveProviderModel(provider: string, model: string, secretRef: string, client: ApiClient = api): Promise<unknown> {
  return client.put("/api/settings/provider", { provider, model, api_key_ref: secretRef });
}

export function saveWorkspacePreferences(preferences: Record<string, string>, client: ApiClient = api): Promise<SettingsResponse> {
  return client.post<SettingsResponse>("/api/settings", { workspace_preferences: preferences });
}

export function booleanPreference(preferences: Record<string, string> | undefined, key: string, fallback = false): boolean {
  const value = preferences?.[key];
  if (value === undefined) return fallback;
  return value === "true";
}

export function getCollaborationSettings(projectId = "default", client: ApiClient = api): Promise<CollaborationSettings> {
  return client.get<CollaborationSettings>(`/api/collaboration/settings?project_id=${encodeURIComponent(projectId)}`);
}

export function saveCollaborationSettings(
  input: { project_id: string; enabled: boolean; sync_server_url: string },
  client: ApiClient = api,
): Promise<CollaborationSettings> {
  return client.post<CollaborationSettings>("/api/collaboration/settings", input);
}

export function listCollaborators(projectId = "default", client: ApiClient = api): Promise<{ collaborators: CollaboratorRecord[] }> {
  return client.get<{ collaborators: CollaboratorRecord[] }>(`/api/collaboration/collaborators?project_id=${encodeURIComponent(projectId)}`);
}

export function inviteCollaborator(
  input: { project_id: string; display_name: string; permission: CollaborationPermission },
  client: ApiClient = api,
): Promise<CollaborationInvite> {
  return client.post<CollaborationInvite>("/api/collaboration/invites", input);
}

export function authenticateCollaborator(
  input: { project_id: string; invite_token: string },
  client: ApiClient = api,
): Promise<CollaborationAuth> {
  return client.post<CollaborationAuth>("/api/collaboration/authenticate", input);
}

export function revokeCollaborator(
  collaboratorId: string,
  projectId = "default",
  client: ApiClient = api,
): Promise<CollaborationRevokeResponse> {
  return client.post<CollaborationRevokeResponse>(`/api/collaboration/collaborators/${encodeURIComponent(collaboratorId)}/revoke`, {
    project_id: projectId,
  });
}
