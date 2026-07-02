import { afterEach, describe, expect, test } from "bun:test";

import { createApiClient, HydraApiError } from "../../lib/api";
import { booleanPreference, looksLikeRawSecret, providerSecretStored, saveProviderModel, saveProviderSecret, saveWorkspacePreferences } from "./settingsController";

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
