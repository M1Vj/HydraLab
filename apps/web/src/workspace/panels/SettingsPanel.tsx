import { useEffect, useState } from "react";
import { Ban, KeyRound, Save, ShieldCheck, UserPlus, Wifi } from "lucide-react";
import type { CollaborationPermission, CollaborationSettings, CollaboratorRecord, SettingsResponse } from "../../lib/api";
import { HydraApiError } from "../../lib/api";
import { useWorkspaceData } from "../data";
import { FailureState, LoadingState, PanelScaffold } from "./PanelState";
import {
  authenticateCollaborator,
  booleanPreference,
  getCollaborationSettings,
  inviteCollaborator,
  listCollaborators,
  looksLikeRawSecret,
  providerSecretStored,
  revokeCollaborator,
  saveCollaborationSettings,
  saveProviderModel,
  saveProviderSecret,
  saveWorkspacePreferences,
} from "./settingsController";
import { AgentAccessModeControl, MemoryContextSurface, SkillsSection } from "./AssistantSettings";
import { McpSettingsSection } from "./McpSettings";
import { PHASE3_MOBILE_FLAG_KEY } from "../../components/mobile/useMobileSurfaceFlag";

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
  const [projectId, setProjectId] = useState("default");
  const [collab, setCollab] = useState<CollaborationSettings | null>(null);
  const [collaborators, setCollaborators] = useState<CollaboratorRecord[]>([]);
  const [collabEnabled, setCollabEnabled] = useState(false);
  const [syncServerUrl, setSyncServerUrl] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [invitePermission, setInvitePermission] = useState<CollaborationPermission>("edit");
  const [lastInviteToken, setLastInviteToken] = useState("");
  const [authInviteToken, setAuthInviteToken] = useState("");
  const [collabBusy, setCollabBusy] = useState<string | null>(null);
  const [collabError, setCollabError] = useState("");

  useEffect(() => {
    void loadCollaboration(projectId);
  }, [projectId]);

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

  async function loadCollaboration(nextProjectId = projectId) {
    setCollabError("");
    try {
      const [settingsPayload, listPayload] = await Promise.all([
        getCollaborationSettings(nextProjectId),
        listCollaborators(nextProjectId),
      ]);
      setCollab(settingsPayload);
      setCollabEnabled(settingsPayload.enabled);
      setSyncServerUrl(settingsPayload.sync_server_url);
      setCollaborators(listPayload.collaborators);
    } catch (caught) {
      setCollabError(caught instanceof Error ? caught.message : "Unable to load collaboration settings");
    }
  }

  async function saveCollaboration() {
    setCollabBusy("settings");
    setCollabError("");
    try {
      const saved = await saveCollaborationSettings({ project_id: projectId, enabled: collabEnabled, sync_server_url: syncServerUrl });
      setCollab(saved);
      void loadCollaboration(projectId);
    } catch (caught) {
      setCollabError(caught instanceof Error ? caught.message : "Unable to save collaboration settings");
    } finally {
      setCollabBusy(null);
    }
  }

  async function createInvite() {
    if (!inviteName.trim()) {
      setCollabError("Enter a collaborator display name.");
      return;
    }
    setCollabBusy("invite");
    setCollabError("");
    try {
      const invite = await inviteCollaborator({ project_id: projectId, display_name: inviteName.trim(), permission: invitePermission });
      setLastInviteToken(invite.invite_token);
      setInviteName("");
      void loadCollaboration(projectId);
    } catch (caught) {
      setCollabError(caught instanceof Error ? caught.message : "Unable to invite collaborator");
    } finally {
      setCollabBusy(null);
    }
  }

  async function authenticateInvite() {
    if (!authInviteToken.trim()) {
      setCollabError("Enter an invite token.");
      return;
    }
    setCollabBusy("authenticate");
    setCollabError("");
    try {
      const auth = await authenticateCollaborator({ project_id: projectId, invite_token: authInviteToken.trim() });
      window.localStorage.setItem("hydra:collaboration:sessionToken", auth.session_token);
      window.localStorage.setItem("hydra:collaboration:displayName", auth.display_name);
      setAuthInviteToken("");
      void loadCollaboration(projectId);
    } catch (caught) {
      setCollabError(caught instanceof Error ? caught.message : "Unable to authenticate invite");
    } finally {
      setCollabBusy(null);
    }
  }

  async function revoke(collaboratorId: string) {
    setCollabBusy(collaboratorId);
    setCollabError("");
    try {
      await revokeCollaborator(collaboratorId, projectId);
      void loadCollaboration(projectId);
    } catch (caught) {
      setCollabError(caught instanceof Error ? caught.message : "Unable to revoke collaborator");
    } finally {
      setCollabBusy(null);
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
            <strong>Phase 3 preview</strong>
          </header>
          <label>
            <input
              type="checkbox"
              checked={booleanPreference(preferences, PHASE3_MOBILE_FLAG_KEY, false)}
              disabled={savingPref === PHASE3_MOBILE_FLAG_KEY}
              onChange={(event) => void togglePreference(PHASE3_MOBILE_FLAG_KEY, event.target.checked)}
            />
            Adaptive phone/tablet surface (Phase 3)
          </label>
          <span className="settings-hint">
            When on, phones and tablets get a simplified companion surface. Desktop is unchanged.
          </span>
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

        <section className="settings-section collaboration-section">
          <header>
            <Wifi size={15} />
            <strong>Collaboration</strong>
            <span className={`status-pill ${collab?.enabled ? "indexed" : ""}`}>{collab?.enabled ? "enabled" : "solo"}</span>
          </header>
          <label className="provider-field">
            Project
            <input value={projectId} onChange={(event) => setProjectId(event.target.value || "default")} />
          </label>
          <label>
            <input type="checkbox" checked={collabEnabled} onChange={(event) => setCollabEnabled(event.target.checked)} />
            Enable project collaboration
          </label>
          <label className="provider-field">
            Self-hosted sync URL
            <input value={syncServerUrl} onChange={(event) => setSyncServerUrl(event.target.value)} placeholder="wss://lab.local:8443" />
          </label>
          <button disabled={collabBusy === "settings"} onClick={() => void saveCollaboration()}>
            <Save size={13} /> Save collaboration
          </button>

          <div className="collaboration-invite-row">
            <input value={inviteName} onChange={(event) => setInviteName(event.target.value)} placeholder="Display name" />
            <select value={invitePermission} onChange={(event) => setInvitePermission(event.target.value as CollaborationPermission)}>
              <option value="read">read</option>
              <option value="comment">comment</option>
              <option value="edit">edit</option>
            </select>
            <button disabled={collabBusy === "invite"} onClick={() => void createInvite()}>
              <UserPlus size={13} /> Invite
            </button>
          </div>
          {lastInviteToken && <input readOnly value={lastInviteToken} aria-label="Latest collaboration invite token" />}

          <div className="collaboration-invite-row">
            <input value={authInviteToken} onChange={(event) => setAuthInviteToken(event.target.value)} placeholder="Invite token" />
            <button disabled={collabBusy === "authenticate"} onClick={() => void authenticateInvite()}>
              <KeyRound size={13} /> Authenticate
            </button>
          </div>

          <div className="collaborator-list" role="list" aria-label="Collaborators">
            {collaborators.length === 0 ? (
              <span className="settings-hint">No collaborators yet.</span>
            ) : (
              collaborators.map((collaborator) => (
                <div key={collaborator.collaborator_id} className="collaborator-row" role="listitem">
                  <div>
                    <strong>{collaborator.display_name}</strong>
                    <span>{collaborator.permission}</span>
                  </div>
                  <button
                    disabled={collaborator.revoked || collabBusy === collaborator.collaborator_id}
                    onClick={() => void revoke(collaborator.collaborator_id)}
                  >
                    <Ban size={13} /> {collaborator.revoked ? "Revoked" : "Revoke"}
                  </button>
                </div>
              ))
            )}
          </div>
          {collabError && (
            <p className="inspector-error" role="alert">{collabError}</p>
          )}
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
        <McpSettingsSection />
        <MemoryContextSurface />
      </div>
    </PanelScaffold>
  );
}
