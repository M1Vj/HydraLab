import { useEffect, useState } from "react";
import { Bot, BrainCircuit, ShieldAlert, Wrench } from "lucide-react";
import {
  api,
  type AssistantModes,
  type ContextFileChange,
  type ReviewItem,
  type SkillsResponse,
} from "../../lib/api";

/** Agent Access Mode control — Passive only; Co-pilot/Full Access disabled "Phase 2". */
export function AgentAccessModeControl() {
  const [modes, setModes] = useState<AssistantModes | null>(null);

  useEffect(() => {
    void api.get<AssistantModes>("/api/assistant/modes").then(setModes).catch(() => setModes(null));
  }, []);

  if (!modes) return null;
  return (
    <section className="settings-section" aria-label="Agent Access Mode">
      <header>
        <Bot size={15} />
        <strong>Agent Access Mode</strong>
      </header>
      <fieldset className="mode-fieldset">
        {modes.modes.map((mode) => (
          <label key={mode.id} className={`mode-option ${mode.enabled ? "" : "disabled"}`}>
            <input
              type="radio"
              name="agent-access-mode"
              value={mode.id}
              checked={modes.default_mode === mode.id}
              disabled={!mode.enabled}
              readOnly
            />
            {mode.label}
            {!mode.enabled && <span className="phase-badge">Phase {mode.phase}</span>}
          </label>
        ))}
      </fieldset>
      <p className="settings-hint">Phase 1 ships Passive (Suggest-only). Every substantive output is a suggestion.</p>
    </section>
  );
}

export function SkillsSection() {
  const [data, setData] = useState<SkillsResponse | null>(null);

  useEffect(() => {
    void api.get<SkillsResponse>("/api/skills").then(setData).catch(() => setData(null));
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
            <li key={skill.id} className={`skill-row ${skill.enabled ? "enabled" : "disabled"}`}>
              <div className="skill-head">
                <strong>{skill.name}</strong>
                <span className="skill-scope">{skill.scope}</span>
              </div>
              <div className="skill-meta">
                <span>risk: {skill.risk_level}</span>
                <span>{skill.requires_approval ? "approval required" : "approval not required"}</span>
                <span>{skill.enabled ? "enabled" : "disabled"}</span>
              </div>
              {skill.disabled_reason && <p className="skill-reason">{skill.disabled_reason}</p>}
            </li>
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
