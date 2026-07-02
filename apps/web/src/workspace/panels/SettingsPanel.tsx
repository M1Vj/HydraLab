import { useState } from "react";
import { KeyRound, Save, ShieldCheck } from "lucide-react";
import type { SettingsResponse } from "../../lib/api";
import { HydraApiError } from "../../lib/api";
import { useWorkspaceData } from "../data";
import { FailureState, LoadingState, PanelScaffold } from "./PanelState";
import { booleanPreference, looksLikeRawSecret, providerSecretStored, saveProviderModel, saveProviderSecret, saveWorkspacePreferences } from "./settingsController";
import { AgentAccessModeControl, MemoryContextSurface, SkillsSection } from "./AssistantSettings";

const CONSENT_TOGGLES: Array<{ key: string; label: string; fallback: boolean }> = [
  { key: "restoreOnLaunch", label: "Session restore on launch", fallback: true },
  { key: "browserPageTextToProvider", label: "Browser page text to provider", fallback: false },
  { key: "offlineOnly", label: "Offline-only provider block", fallback: false },
];

const AUTOMATION_TOGGLES: Array<{ key: string; label: string; fallback: boolean }> = [
  { key: "auto_draft_tasks", label: "Auto-create low-risk draft tasks", fallback: false },
  { key: "auto_checkpoint", label: "Auto-checkpoint Git before risky actions", fallback: false },
];

export function SettingsPanel() {
  const { settings } = useWorkspaceData();
  const [secretDrafts, setSecretDrafts] = useState<Record<string, string>>({});
  const [modelDrafts, setModelDrafts] = useState<Record<string, string>>({});
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [savingPref, setSavingPref] = useState<string | null>(null);
  const [rowError, setRowError] = useState<Record<string, string>>({});

  if (settings.status === "loading" && !settings.data) return <LoadingState title="Loading settings" />;
  if (settings.status === "failure") return <FailureState error={settings.error} onRetry={settings.reload} />;

  const payload = settings.data as SettingsResponse | null;
  const providers = payload?.provider_settings ?? [];
  const preferences = payload?.workspace_preferences;

  function setError(provider: string, message: string) {
    setRowError((current) => ({ ...current, [provider]: message }));
  }

  async function submitSecret(provider: string) {
    const secret = secretDrafts[provider] ?? "";
    if (!secret.trim()) {
      setError(provider, "Enter a secret to store.");
      return;
    }
    setError(provider, "");
    setBusyProvider(provider);
    try {
      await saveProviderSecret(provider, secret);
      // Write-only: clear the field so a stored secret is never echoed back.
      setSecretDrafts((current) => ({ ...current, [provider]: "" }));
      settings.reload();
    } catch (caught) {
      setError(provider, caught instanceof Error ? caught.message : "Unable to store secret");
    } finally {
      setBusyProvider(null);
    }
  }

  async function submitModel(provider: string, secretRef: string) {
    const model = (modelDrafts[provider] ?? "").trim();
    if (!model) {
      setError(provider, "Enter a model identifier.");
      return;
    }
    if (looksLikeRawSecret(model)) {
      setError(provider, "That looks like a raw secret. Store it in the secret field instead.");
      return;
    }
    setError(provider, "");
    setBusyProvider(provider);
    try {
      await saveProviderModel(provider, model, secretRef);
      setModelDrafts((current) => ({ ...current, [provider]: "" }));
      settings.reload();
    } catch (caught) {
      const message = caught instanceof HydraApiError ? caught.message : caught instanceof Error ? caught.message : "Unable to save provider";
      setError(provider, message);
    } finally {
      setBusyProvider(null);
    }
  }

  async function togglePreference(key: string, next: boolean) {
    setSavingPref(key);
    try {
      await saveWorkspacePreferences({ [key]: String(next) });
      settings.reload();
    } finally {
      setSavingPref(null);
    }
  }

  return (
    <PanelScaffold title="Settings">
      <div className="settings-grid">
        <AgentAccessModeControl />
        <section className="settings-section">
          <header>
            <ShieldCheck size={15} />
            <strong>Consent and capture</strong>
          </header>
          {CONSENT_TOGGLES.map((toggle) => (
            <label key={toggle.key}>
              <input
                type="checkbox"
                checked={booleanPreference(preferences, toggle.key, toggle.fallback)}
                disabled={savingPref === toggle.key}
                onChange={(event) => void togglePreference(toggle.key, event.target.checked)}
              />
              {toggle.label}
            </label>
          ))}
        </section>

        <section className="settings-section">
          <header>
            <ShieldCheck size={15} />
            <strong>Task &amp; Git automation</strong>
          </header>
          {AUTOMATION_TOGGLES.map((toggle) => (
            <label key={toggle.key}>
              <input
                type="checkbox"
                checked={booleanPreference(preferences, toggle.key, toggle.fallback)}
                disabled={savingPref === toggle.key}
                onChange={(event) => void togglePreference(toggle.key, event.target.checked)}
              />
              {toggle.label}
            </label>
          ))}
        </section>

        <section className="settings-section">
          <header>
            <KeyRound size={15} />
            <strong>Providers</strong>
          </header>
          {providers.length === 0 ? (
            <span className="settings-hint">No providers configured yet.</span>
          ) : (
            providers.map((provider) => {
              const stored = providerSecretStored(provider);
              const secretRef = provider.secret_ref || provider.api_key_ref || "";
              const busy = busyProvider === provider.provider;
              return (
                <div key={provider.provider} className="provider-card">
                  <div className="provider-row">
                    <strong>{provider.provider}</strong>
                    <span className={`secret-status ${stored ? "stored" : "unset"}`}>{stored ? "stored ✓" : "not set"}</span>
                  </div>
                  <label className="provider-field">
                    Model
                    <input
                      value={modelDrafts[provider.provider] ?? provider.model ?? ""}
                      onChange={(event) => setModelDrafts((current) => ({ ...current, [provider.provider]: event.target.value }))}
                      placeholder="gpt-4.1"
                    />
                  </label>
                  <label className="provider-field">
                    Secret (write-only)
                    <input
                      type="password"
                      autoComplete="off"
                      value={secretDrafts[provider.provider] ?? ""}
                      onChange={(event) => setSecretDrafts((current) => ({ ...current, [provider.provider]: event.target.value }))}
                      placeholder={stored ? "Replace stored secret" : "Enter provider secret"}
                    />
                  </label>
                  <div className="provider-actions">
                    <button disabled={busy} onClick={() => void submitSecret(provider.provider)}>
                      <KeyRound size={13} /> Store secret
                    </button>
                    <button disabled={busy} onClick={() => void submitModel(provider.provider, secretRef)}>
                      <Save size={13} /> Save model
                    </button>
                  </div>
                  {rowError[provider.provider] && (
                    <p className="inspector-error" role="alert">{rowError[provider.provider]}</p>
                  )}
                </div>
              );
            })
          )}
        </section>

        <SkillsSection />
        <MemoryContextSurface />
      </div>
    </PanelScaffold>
  );
}
