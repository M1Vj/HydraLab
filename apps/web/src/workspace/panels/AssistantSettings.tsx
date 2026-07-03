import { useEffect, useState } from "react";
import { Bot, BrainCircuit, RotateCcw, ShieldAlert, Wrench } from "lucide-react";
import {
  api,
  type AssistantModes,
  type ContextFileChange,
  type ReviewItem,
  type SkillInfo,
  type SkillsResponse,
} from "../../lib/api";
import { editSkill, fetchModes, restoreSkillDefault, setFullAccess, setMode, toggleSkill } from "./agentController";

const PROJECT_ID = "default";

/** Agent Access Mode control — Passive/Co-pilot selectable; Full Access per-project opt-in. */
export function AgentAccessModeControl() {
  const [modes, setModes] = useState<AssistantModes | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setModes(await fetchModes(PROJECT_ID));
    } catch {
      setModes(null);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function chooseMode(mode: string) {
    setBusy(true);
    setError(null);
    try {
      await setMode(mode, PROJECT_ID);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to set mode");
    } finally {
      setBusy(false);
    }
  }

  async function toggleFullAccess(enabled: boolean) {
    setBusy(true);
    setError(null);
    try {
      await setFullAccess(enabled, PROJECT_ID);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to change Full Access");
    } finally {
      setBusy(false);
    }
  }

  if (!modes) return null;
  return (
    <section className="settings-section" aria-label="Agent Access Mode">
      <header>
        <Bot size={15} />
        <strong>Agent Access Mode</strong>
      </header>
      <fieldset className="mode-fieldset" disabled={busy}>
        {modes.modes.map((mode) => (
          <label key={mode.id} className={`mode-option ${mode.enabled ? "" : "disabled"}`}>
            <input
              type="radio"
              name="agent-access-mode"
              value={mode.id}
              checked={modes.default_mode === mode.id}
              disabled={!mode.enabled}
              onChange={() => void chooseMode(mode.id)}
            />
            {mode.label}
            {!mode.enabled && <span className="phase-badge">Phase {mode.phase}</span>}
          </label>
        ))}
      </fieldset>
      <label className="full-access-optin">
        <input
          type="checkbox"
          checked={modes.full_access_enabled}
          disabled={busy}
          onChange={(event) => void toggleFullAccess(event.target.checked)}
        />
        Enable Full Access (YOLO) for this project
      </label>
      <p className="settings-hint">
        Passive suggests only. Co-pilot asks per item. Full Access auto-applies low-risk writes with a
        before/after checkpoint, and is OFF until explicitly enabled per project.
      </p>
      {error && <p className="inspector-error" role="alert">{error}</p>}
    </section>
  );
}

function SkillRow({ skill, onChanged }: { skill: SkillInfo; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(skill.body ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function onToggle(enabled: boolean) {
    setBusy(true);
    setMessage(null);
    try {
      await toggleSkill(skill.id, enabled);
      onChanged();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Unable to toggle skill");
    } finally {
      setBusy(false);
    }
  }

  async function onSave() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await editSkill(skill.id, draft);
      setMessage(result.validation_error ? `Invalid: ${result.validation_error}` : "Saved");
      setEditing(false);
      onChanged();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Unable to save skill");
    } finally {
      setBusy(false);
    }
  }

  async function onRestore() {
    setBusy(true);
    setMessage(null);
    try {
      await restoreSkillDefault(skill.id);
      setMessage("Restored to factory default");
      setEditing(false);
      onChanged();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Unable to restore skill");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className={`skill-row ${skill.enabled ? "enabled" : "disabled"}`}>
      <div className="skill-head">
        <strong>{skill.name}</strong>
        <span className="skill-scope">{skill.scope}</span>
        {skill.edited && <span className="skill-edited-badge">edited</span>}
      </div>
      <div className="skill-meta">
        <span>risk: {skill.risk_level}</span>
        <span>{skill.requires_approval ? "approval required" : "approval not required"}</span>
        <label className="skill-enable-toggle">
          <input
            type="checkbox"
            checked={skill.enabled}
            disabled={busy || Boolean(skill.disabled_reason)}
            onChange={(event) => void onToggle(event.target.checked)}
          />
          enabled
        </label>
      </div>
      {skill.disabled_reason && <p className="skill-reason">{skill.disabled_reason}</p>}
      <div className="skill-actions">
        <button type="button" disabled={busy} onClick={() => { setDraft(skill.body ?? ""); setEditing((value) => !value); }}>
          {editing ? "Cancel" : "Edit"}
        </button>
        {skill.restorable && (
          <button type="button" disabled={busy} onClick={() => void onRestore()}>
            <RotateCcw size={12} /> Restore default
          </button>
        )}
      </div>
      {editing && (
        <div className="skill-editor">
          <textarea
            aria-label={`Edit ${skill.name}`}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={8}
          />
          <button type="button" disabled={busy} onClick={() => void onSave()}>Save</button>
        </div>
      )}
      {message && <p className="skill-message" role="status">{message}</p>}
    </li>
  );
}

export function SkillsSection() {
  const [data, setData] = useState<SkillsResponse | null>(null);

  function load() {
    void api.get<SkillsResponse>("/api/skills").then(setData).catch(() => setData(null));
  }

  useEffect(() => {
    load();
  }, []);

  if (!data) return null;
  return (
    <section className="settings-section" aria-label="Skills">
      <header>
        <Wrench size={15} />
        <strong>Skills</strong>
      </header>
      {data.skills.length === 0 ? (
        <span className="settings-hint">No skills loaded.</span>
      ) : (
        <ul className="skill-list">
          {data.skills.map((skill) => (
            <SkillRow key={skill.id} skill={skill} onChanged={load} />
          ))}
        </ul>
      )}
      {data.rejected_plugins.length > 0 && (
        <p className="settings-hint" role="alert">
          <ShieldAlert size={12} /> {data.rejected_plugins[0].reason}
        </p>
      )}
    </section>
  );
}

export function MemoryContextSurface() {
  const [changes, setChanges] = useState<ContextFileChange[]>([]);
  const [candidates, setCandidates] = useState<ReviewItem[]>([]);

  async function load() {
    try {
      const changePayload = await api.get<{ changes: ContextFileChange[] }>("/api/context-files/changes?project_id=default");
      setChanges(changePayload.changes);
    } catch {
      setChanges([]);
    }
    try {
      const review = await api.get<{ items: ReviewItem[] }>("/api/review-inbox?project_id=default");
      setCandidates(review.items.filter((item) => item.item_type === "memory-candidate"));
    } catch {
      setCandidates([]);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <section className="settings-section" aria-label="Memory and Context">
      <header>
        <BrainCircuit size={15} />
        <strong>Memory / Context</strong>
      </header>

      <h4>Recent context-file changes</h4>
      {changes.length === 0 ? (
        <span className="settings-hint">No recorded context-file changes yet.</span>
      ) : (
        <ul className="context-change-list">
          {changes.map((change) => (
            <li key={change.id} className={`context-change trust-${change.trust_level}`}>
              <strong>{change.file}</strong>
              <span className="change-label">{change.recovery === "logs-only" ? "logs-only" : "Git/checkpoint-backed"}</span>
              <span>provenance: {change.provenance}</span>
              <span>trust: {change.trust_level}</span>
              {change.checkpoint_ref && <span>recovery point: {change.checkpoint_ref}</span>}
              <time>{new Date(change.created_at * 1000).toLocaleTimeString()}</time>
            </li>
          ))}
        </ul>
      )}

      <h4>Memory candidates</h4>
      {candidates.length === 0 ? (
        <span className="settings-hint">No memory candidates awaiting review.</span>
      ) : (
        <ul className="memory-candidate-list">
          {candidates.map((candidate) => {
            const payload = (candidate.payload ?? {}) as Record<string, unknown>;
            return (
              <li key={candidate.id} className="memory-candidate">
                <p className="candidate-fact">{String(payload.fact ?? candidate.summary)}</p>
                <div className="candidate-meta">
                  <span>→ {String(payload.destination ?? "MEMORY.md")}</span>
                  <span>confidence: {String(payload.confidence ?? "n/a")}</span>
                  <span>source: {String(payload.source_ref ?? candidate.origin_id ?? "n/a")}</span>
                  {payload.trust_origin === "untrusted-external" && <span className="untrusted-tag">untrusted-external</span>}
                </div>
                <div className="candidate-actions">
                  <button>Accept</button>
                  <button>Reject</button>
                  <button>Edit</button>
                  <button>Never remember this</button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
