import { afterEach, describe, expect, test } from "bun:test";

import { createApiClient, HydraApiError } from "../../lib/api";
import {
  authenticateCollaborator,
  booleanPreference,
  fetchSelfEvolutionAudit,
  inviteCollaborator,
  looksLikeRawSecret,
  providerSecretStored,
  revokeCollaborator,
  saveCollaborationSettings,
  saveProviderModel,
  saveProviderSecret,
  saveWorkspacePreferences,
} from "./settingsController";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("secret status helpers", () => {
  test("looksLikeRawSecret flags raw provider keys", () => {
    expect(looksLikeRawSecret("sk-abc123")).toBe(true);
    expect(looksLikeRawSecret("ghp_token")).toBe(true);
    expect(looksLikeRawSecret("keychain:hydralab/openai")).toBe(false);
    expect(looksLikeRawSecret("")).toBe(false);
  });

  test("providerSecretStored reflects resolved references", () => {
    expect(providerSecretStored({ secret_ref: "keychain:hydralab/openai", resolved: true, auth_status: undefined })).toBe(true);
    expect(providerSecretStored({ secret_ref: null, resolved: false, auth_status: undefined })).toBe(false);
    expect(providerSecretStored({ secret_ref: null, resolved: false, auth_status: "ready" })).toBe(true);
  });

  test("booleanPreference parses stored string flags", () => {
    expect(booleanPreference({ restoreOnLaunch: "true" }, "restoreOnLaunch")).toBe(true);
    expect(booleanPreference({ restoreOnLaunch: "false" }, "restoreOnLaunch")).toBe(false);
    expect(booleanPreference(undefined, "restoreOnLaunch", true)).toBe(true);
  });
});

describe("settings secret-write flow", () => {
  test("secret POST hits the keychain-only route and returns the reference", async () => {
    let captured: { url: string; body: unknown } | null = null;
    globalThis.fetch = async (input, init) => {
      captured = { url: String(input), body: JSON.parse(String(init?.body ?? "{}")) };
      return jsonResponse({ secret_ref: "keychain:hydralab/openai" });
    };
    const client = createApiClient("/api", 100);

    const result = await saveProviderSecret("openai", "sk-super-secret", client);

    expect(result.secret_ref).toBe("keychain:hydralab/openai");
    expect(captured!.url).toContain("/api/settings/provider/secret");
    expect(captured!.body).toEqual({ provider: "openai", secret: "sk-super-secret" });
  });

  test("provider model save with a raw-secret-looking value surfaces the backend 400", async () => {
    globalThis.fetch = async () =>
      jsonResponse(
        { detail: "Provider 'openai' credentials must be saved as keychain:* or env:* references. Send raw secrets to POST /api/settings/provider/secret first." },
        400,
      );
    const client = createApiClient("/api", 100);

    const failure = saveProviderModel("openai", "gpt-4.1", "sk-not-a-reference", client);
    await expect(failure).rejects.toBeInstanceOf(HydraApiError);
    await expect(failure).rejects.toMatchObject({ status: 400 });
    await expect(failure).rejects.toThrow(/keychain:\* or env:\* references/);
  });

  test("workspace preferences post the consent toggle payload", async () => {
    let capturedBody: unknown = null;
    globalThis.fetch = async (_input, init) => {
      capturedBody = JSON.parse(String(init?.body ?? "{}"));
      return jsonResponse({ provider_settings: [], workspace_preferences: { offlineOnly: "true" }, global_settings: {} });
    };
    const client = createApiClient("/api", 100);

    const response = await saveWorkspacePreferences({ offlineOnly: "true" }, client);

    expect(capturedBody).toEqual({ workspace_preferences: { offlineOnly: "true" } });
    expect(response.workspace_preferences.offlineOnly).toBe("true");
  });
});

describe("collaboration settings flow", () => {
  test("collaboration opt-in posts the self-hosted sync URL", async () => {
    let capturedBody: unknown = null;
    globalThis.fetch = async (_input, init) => {
      capturedBody = JSON.parse(String(init?.body ?? "{}"));
      return jsonResponse({ project_id: "transformer-survey", enabled: true, sync_server_url: "wss://lab.local:8443", sync_server_kind: "self-hosted" });
    };
    const client = createApiClient("/api", 100);

    const result = await saveCollaborationSettings({ project_id: "transformer-survey", enabled: true, sync_server_url: "wss://lab.local:8443" }, client);

    expect(capturedBody).toEqual({ project_id: "transformer-survey", enabled: true, sync_server_url: "wss://lab.local:8443" });
    expect(result.sync_server_kind).toBe("self-hosted");
  });

  test("self-evolution audit history hits the audit endpoint", async () => {
    let capturedUrl = "";
    globalThis.fetch = async (input) => {
      capturedUrl = String(input);
      return jsonResponse({ entries: [{ id: "a1", action: "self_evolution.applied", actor: "user", risk_level: "medium", target: "chg-1:prompt:-:skills/x.md", approval_state: "applied", created_at: 0 }] });
    };
    const client = createApiClient("/api", 100);
    const result = await fetchSelfEvolutionAudit("default", client);
    expect(capturedUrl).toBe("/api/self-evolution/audit?project_id=default");
    expect(result.entries[0].action).toBe("self_evolution.applied");
  });

  test("invite, authenticate, and revoke use collaboration endpoints", async () => {
    const urls: string[] = [];
    globalThis.fetch = async (input, init) => {
      urls.push(String(input));
      const body = JSON.parse(String(init?.body ?? "{}"));
      if (String(input).includes("/invites")) return jsonResponse({ collaborator_id: "c1", permission: body.permission, invite_token: "invite-token" });
      if (String(input).includes("/authenticate")) {
        return jsonResponse({ collaborator_id: "c1", display_name: "Dana Reyes", permission: "edit", session_token: "session-token" });
      }
      return jsonResponse({ collaborator_id: "c1", revoked: true, disconnected: 1 });
    };
    const client = createApiClient("/api", 100);

    const invite = await inviteCollaborator({ project_id: "transformer-survey", display_name: "Dana Reyes", permission: "edit" }, client);
    const auth = await authenticateCollaborator({ project_id: "transformer-survey", invite_token: invite.invite_token }, client);
    const revoked = await revokeCollaborator("c1", "transformer-survey", client);

    expect(auth.display_name).toBe("Dana Reyes");
    expect(revoked.revoked).toBe(true);
    expect(urls).toEqual([
      "/api/collaboration/invites",
      "/api/collaboration/authenticate",
      "/api/collaboration/collaborators/c1/revoke",
    ]);
  });
});
