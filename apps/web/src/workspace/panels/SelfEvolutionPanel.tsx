import { useEffect, useState } from "react";
import { Check, ShieldAlert, X } from "lucide-react";
import type { PanelComponentProps } from "../panelRegistry";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";
import {
  approveDisabledReason,
  approveSelfEvolutionChange,
  canApprove,
  denySelfEvolutionChange,
  listSelfEvolutionChanges,
  riskBadge,
  statusBadge,
  trustBadge,
  type Badge,
  type SelfEvolutionChange,
} from "./selfEvolutionController";

function BadgePill({ badge }: { badge: Badge }) {
  return (
    <small className={`status-pill tone-${badge.tone}`} data-tone={badge.tone}>
      {badge.label}
    </small>
  );
}

export function SelfEvolutionPanel({ announce, openPanel }: PanelComponentProps) {
  const [changes, setChanges] = useState<SelfEvolutionChange[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [rowError, setRowError] = useState<Record<string, string>>({});

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const payload = await listSelfEvolutionChanges("default");
      setChanges(payload.changes);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setLoading(false);
    }
  }

  async function approve(change: SelfEvolutionChange) {
    setBusy(change.change_id);
    setRowError((current) => ({ ...current, [change.change_id]: "" }));
    try {
      const { change: updated } = await approveSelfEvolutionChange(change.change_id);
      setChanges((current) => current.map((item) => (item.change_id === updated.change_id ? updated : item)));
      announce(updated.status === "applied" ? "Change applied and verified" : `Change ${updated.status}`);
    } catch (caught) {
      setRowError((current) => ({ ...current, [change.change_id]: caught instanceof Error ? caught.message : "Approve failed" }));
    } finally {
      setBusy(null);
    }
  }

  async function deny(change: SelfEvolutionChange) {
    setBusy(change.change_id);
    setRowError((current) => ({ ...current, [change.change_id]: "" }));
    try {
      const { change: updated } = await denySelfEvolutionChange(change.change_id);
      setChanges((current) => current.map((item) => (item.change_id === updated.change_id ? updated : item)));
      announce("Change denied; nothing was written");
    } catch (caught) {
      setRowError((current) => ({ ...current, [change.change_id]: caught instanceof Error ? caught.message : "Deny failed" }));
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <LoadingState title="Loading self-evolution proposals" />;
  if (error) return <FailureState error={error} onRetry={load} />;
  if (changes.length === 0) {
    return (
      <EmptyState
        title="No self-evolution proposals"
        message="Proposed skill, prompt, setting and app-code change-sets will appear here for review, approval, checkpoint, apply and auto-verify."
        action="Refresh"
        onAction={() => void load()}
      />
    );
  }

  return (
    <PanelScaffold title="Self-Evolution">
      <p className="panel-hint" role="note">
        Every change is applied only through approve → checkpoint → apply → auto-verify → keep-or-rollback. Protected-field and
        untrusted-external diffs route to the Review Inbox and never auto-apply.
      </p>
      <div className="object-list">
        {changes.map((change) => {
          const disabled = approveDisabledReason(change);
          const routed = change.review_inbox;
          return (
            <article className="object-card self-evolution-change" key={change.change_id} aria-label={`Change ${change.change_id}`}>
              <header className="self-evolution-head">
                <strong>{change.target_path}</strong>
                <span className="category-badge">{change.category}</span>
              </header>
              <div className="badge-row">
                <BadgePill badge={statusBadge(change)} />
                <BadgePill badge={riskBadge(change)} />
                <BadgePill badge={trustBadge(change)} />
                {change.verification_result && <BadgePill badge={{ label: `verify: ${change.verification_result}`, tone: change.verification_result === "pass" ? "ok" : "warn" }} />}
              </div>
              <pre className="diff-view" aria-label={`Diff for ${change.target_path}`}>
                {change.unified_diff || "(no diff preview)"}
              </pre>
              <div className="test-plan">
                <span className="test-plan-label">Test plan:</span>
                {change.test_plan.length === 0 ? (
                  <em>none — not approvable</em>
                ) : (
                  <ul>
                    {change.test_plan.map((command) => (
                      <li key={command}><code>{command}</code></li>
                    ))}
                  </ul>
                )}
              </div>
              {routed && (
                <button className="review-route" onClick={() => openPanel("review-inbox")}>
                  <ShieldAlert size={13} /> Routed to Review Inbox — open
                </button>
              )}
              <div className="task-badge-actions">
                <button
                  onClick={() => void approve(change)}
                  disabled={!canApprove(change) || busy === change.change_id}
                  title={disabled ?? "Approve, checkpoint, apply and verify"}
                  aria-label={`Approve change ${change.change_id}`}
                >
                  <Check size={13} /> Approve &amp; apply
                </button>
                <button
                  onClick={() => void deny(change)}
                  disabled={busy === change.change_id || change.status === "denied" || change.status === "applied"}
                  aria-label={`Deny change ${change.change_id}`}
                >
                  <X size={13} /> Deny
                </button>
              </div>
              {disabled && change.status === "proposed" && <small className="settings-hint">{disabled}</small>}
              {rowError[change.change_id] && (
                <p className="inspector-error" role="alert">{rowError[change.change_id]}</p>
              )}
            </article>
          );
        })}
      </div>
    </PanelScaffold>
  );
}
