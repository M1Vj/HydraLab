import { api, type ApiClient, type SettingsResponse } from "../../lib/api";

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
