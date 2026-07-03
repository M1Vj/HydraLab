import { type FormEvent, useEffect, useState } from "react";
import { Download, GitCommitHorizontal, RotateCcw } from "lucide-react";
import {
  api,
  createCitation,
  type BrowserEventRecord,
  type SourceRecord,
  type GitCommit,
  type GitCommitSuggestion,
  type GitStatusResponse,
} from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { useWorkspaceData } from "../data";
import { EmptyState, FailureState, LoadingState, NotWiredState, PanelScaffold } from "./PanelState";
import {
  citationMissingMetadata,
  claimStatusBadge,
  evidenceSupportBadge,
  inlineBadgesForSource,
  summarizeCitationEvidence,
  type StatusBadge,
} from "./citationEvidence";

export { PdfReaderPanel } from "./PdfReaderPanel";
export { SettingsPanel } from "./SettingsPanel";
export { TerminalPanel } from "./TerminalPanel";
export { ExportPanel } from "./ExportPanel";

function StatusPill({ badge }: { badge: StatusBadge }) {
  return (
    <small className={`status-pill tone-${badge.tone}`} data-tone={badge.tone}>
      <span aria-hidden="true">{badge.symbol}</span> {badge.label}
    </small>
  );
}

function CiteSourceForm({
  sources,
  projectId,
  onCreated,
  announce,
}: {
  sources: SourceRecord[];
  projectId: string;
  onCreated: () => void;
  announce: (message: string) => void;
}) {
  const [sourceId, setSourceId] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeSourceId = sources.some((source) => source.id === sourceId) ? sourceId : sources[0]?.id ?? "";
  const canSubmit = activeSourceId !== "" && text.trim() !== "" && !busy;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await createCitation({ source_id: activeSourceId, text: text.trim(), project_id: projectId });
      setText("");
      announce("Citation added");
      onCreated();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="cite-source-form" onSubmit={submit} aria-label="Cite a saved source">
      <label>
        <span>Cite a saved source</span>
        <select value={activeSourceId} onChange={(event) => setSourceId(event.target.value)} disabled={busy}>
          {sources.map((source) => (
            <option key={source.id} value={source.id}>
              {source.title || source.id}
              {source.year ? ` (${source.year})` : ""}
            </option>
          ))}
        </select>
      </label>
      <textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="Citation text or pin-cite (e.g. p. 12, §3)"
        rows={2}
        disabled={busy}
        aria-label="Citation text"
      />
      {error && (
        <small className="status-pill tone-danger" role="alert" data-tone="danger">
          <span aria-hidden="true">✗</span> {error}
        </small>
      )}
      <button type="submit" disabled={!canSubmit}>
        {busy ? "Adding…" : "Add citation"}
      </button>
    </form>
  );
}

export function CitationEvidencePanel({ openPanel, announce }: PanelComponentProps) {
  const { projectId, objects, review } = useWorkspaceData();
  if (objects.status === "loading" && !objects.data) return <LoadingState title="Loading evidence graph" />;
  if (objects.status === "failure") return <FailureState error={objects.error} onRetry={objects.reload} />;
  const data = objects.data;
  const summary = data
    ? summarizeCitationEvidence(data.objects)
    : { claims: 0, citations: 0, evidence: 0, unsupportedClaims: 0, isEmpty: true };
  const citableSources = (data?.objects.sources ?? []).filter((source) => !source.trashed);
  if (!data || summary.isEmpty) {
    if (citableSources.length === 0) {
      return (
        <EmptyState
          title="No citations yet"
          message="Save or import a source first — then you can cite it here."
          action="Open source discovery"
          onAction={() => openPanel("source-discovery")}
        />
      );
    }
    return (
      <PanelScaffold title="Citation & Evidence">
        <div className="object-list">
          <p className="panel-hint" role="status">
            No citations yet. Cite one of your {citableSources.length} saved source(s) to begin.
          </p>
          <CiteSourceForm sources={citableSources} projectId={projectId} onCreated={objects.reload} announce={announce} />
        </div>
      </PanelScaffold>
    );
  }
  const reviewItems = review.data?.items ?? [];
  const sourcesById = new Map<string, SourceRecord>(data.objects.sources.map((source) => [source.id, source]));

  return (
    <PanelScaffold title="Citation & Evidence">
      <div className="object-list">
        {citableSources.length > 0 && (
          <CiteSourceForm sources={citableSources} projectId={projectId} onCreated={objects.reload} announce={announce} />
        )}
        {summary.unsupportedClaims > 0 && (
          <p className="panel-hint" role="status">
            {summary.unsupportedClaims} of {summary.claims} claim(s) are not yet supported by reviewed evidence.
          </p>
        )}
        {data.objects.claims.map((claim) => (
          <article className="object-card" key={claim.id}>
            <strong>{claim.claim_text ?? claim.text}</strong>
            <StatusPill badge={claimStatusBadge(claim)} />
          </article>
        ))}
        {data.objects.evidence.map((evidence) => (
          <article className="object-card" key={evidence.id}>
            <StatusPill badge={evidenceSupportBadge(evidence)} />
            <span>{evidence.quote_text ?? evidence.passage}</span>
            <button onClick={() => openPanel("pdf-reader", { sourceId: evidence.source_id, title: evidence.source_title ?? evidence.source_id })}>Go to origin</button>
          </article>
        ))}
        {data.objects.citations.map((citation) => {
          const missing = citationMissingMetadata(sourcesById.get(citation.source_id));
          const badges = inlineBadgesForSource(reviewItems, citation.source_id);
          return (
            <article className="object-card" key={citation.id}>
              <strong>{citation.citation_key || citation.source_id}</strong>
              <span>{citation.text}</span>
              {missing.length > 0 && (
                <small className="status-pill tone-warn" data-tone="warn">
                  <span aria-hidden="true">!</span> Missing metadata: {missing.join(", ")}
                </small>
              )}
              {badges.map((badge) => (
                <button
                  key={badge.reviewItemId}
                  className={`inline-badge badge-${badge.kind}`}
                  onClick={() => openPanel("review-inbox", { objectId: badge.reviewItemId })}
                >
                  {badge.label}
                </button>
              ))}
            </article>
          );
        })}
      </div>
    </PanelScaffold>
  );
}

export function ReviewInboxPanel({ openPanel }: PanelComponentProps) {
  const { review } = useWorkspaceData();
  if (review.status === "loading" && !review.data) return <LoadingState title="Loading review inbox" />;
  if (review.status === "failure") return <FailureState error={review.error} onRetry={review.reload} />;
  const items = review.data?.items ?? [];
  if (items.length === 0) return <EmptyState title="All clear" message="No pending recovery, browser, evidence, citation or warning items need review." />;
  return (
    <PanelScaffold title="Review Inbox">
      <div className="object-list">
        {items.map((item) => (
          <article className="object-card review-item" key={item.id}>
            <span className="origin-badge">{item.origin_type ?? item.item_type}</span>
            <strong>{item.title}</strong>
            {item.summary && <p>{item.summary}</p>}
            <button onClick={() => openPanel(item.target_type === "source" ? "citation-evidence" : "markdown-editor", { objectId: item.target_id ?? item.id })}>
              Open origin
            </button>
          </article>
        ))}
      </div>
    </PanelScaffold>
  );
}

export function BrowserPanel() {
  const [events, setEvents] = useState<BrowserEventRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    void loadLedger();
  }, []);

  async function loadLedger() {
    setLoading(true);
    setError(null);
    try {
      const payload = await api.get<{ events: BrowserEventRecord[] }>("/api/browser/ledger?project_id=default");
      setEvents(payload.events);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <LoadingState title="Loading browser ledger" />;
  if (error) return <FailureState error={error} onRetry={loadLedger} />;
  if (events.length === 0) return <EmptyState title="No browser context" message="Browser ledger is empty or the extension bridge has not been paired." action="Retry" onAction={() => void loadLedger()} />;
  return (
    <PanelScaffold title="Browser">
      <div className="object-list">
        {events.map((event) => (
          <article className="object-card" key={event.id}>
            <strong>{event.title || event.url}</strong>
            <span>{event.url}</span>
            <small>{event.event_type}</small>
          </article>
        ))}
      </div>
    </PanelScaffold>
  );
}

export function LogsPanel() {
  const { events } = useWorkspaceData();
  if (events.status === "loading" && !events.data) return <LoadingState title="Loading logs" />;
  if (events.status === "failure") return <FailureState error={events.error} onRetry={events.reload} />;
  const rows = events.data?.events ?? [];
  return (
    <PanelScaffold title="Logs">
      {rows.length === 0 ? (
        <EmptyState title="No events" message="Backend activity events will appear here." />
      ) : (
        <pre className="event-log">{rows.map((event) => `${event.kind}: ${event.message}`).join("\n")}</pre>
      )}
    </PanelScaffold>
  );
}

export function ProblemsPanel() {
  const { objects, tree, review, events, settings } = useWorkspaceData();
  const problems = [objects, tree, review, events, settings].filter((resource) => resource.status === "failure");
  if (problems.length === 0) return <EmptyState title="No problems" message="Panel failures and backend errors will appear here." />;
  return (
    <PanelScaffold title="Problems">
      <div className="object-list">
        {problems.map((problem, index) => (
          <article className="object-card" key={index}>
            <strong>{problem.status}</strong>
            {"error" in problem && problem.error && <span>{problem.error.message}</span>}
          </article>
        ))}
      </div>
    </PanelScaffold>
  );
}

export function GitPanel({ announce }: PanelComponentProps) {
  const [status, setStatus] = useState<GitStatusResponse | null>(null);
  const [commits, setCommits] = useState<GitCommit[]>([]);
  const [suggestions, setSuggestions] = useState<GitCommitSuggestion[]>([]);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [statusPayload, logPayload, suggestPayload] = await Promise.all([
        api.get<GitStatusResponse>("/api/git/status"),
        api.get<{ commits: GitCommit[] }>("/api/git/log"),
        api.get<{ suggestions: GitCommitSuggestion[] }>("/api/git/suggest-commits"),
      ]);
      setStatus(statusPayload);
      setCommits(logPayload.commits);
      setSuggestions(suggestPayload.suggestions);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setLoading(false);
    }
  }

  async function commit(message: string) {
    try {
      await api.post("/api/git/commit", { message });
      announce("Committed changes");
      void load();
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  if (loading) return <LoadingState title="Loading Git" />;
  if (error) return <FailureState error={error} onRetry={load} />;
  if (!status?.is_repo) {
    return <NotWiredState title="Git" route="No Git repository for this project" />;
  }

  return (
    <PanelScaffold title="Git">
      <header className="panel-toolbar">
        <span className="git-branch">branch: {status.branch}</span>
      </header>
      <section className="git-status">
        <h3>Changed files</h3>
        {status.changed_files.length === 0 ? (
          <p className="settings-hint">Working tree clean.</p>
        ) : (
          <ul className="git-file-list">
            {status.changed_files.map((file) => (
              <li key={file.path}>
                <code>{file.code}</code> {file.path}
              </li>
            ))}
          </ul>
        )}
      </section>
      {suggestions.length > 0 && (
        <section className="git-suggestions">
          <h3>Suggested commits</h3>
          {suggestions.map((suggestion) => (
            <article className="object-card" key={suggestion.message}>
              <strong>{suggestion.message}</strong>
              <small>{suggestion.files.join(", ")}</small>
              <button onClick={() => void commit(suggestion.message)}>
                <GitCommitHorizontal size={13} /> Commit
              </button>
            </article>
          ))}
        </section>
      )}
      <section className="git-history">
        <h3>History</h3>
        <ul className="git-file-list">
          {commits.map((entry) => (
            <li key={entry.hash}>
              <RotateCcw size={12} aria-hidden /> {entry.subject}
            </li>
          ))}
        </ul>
      </section>
    </PanelScaffold>
  );
}

export function ExportBibliographyButton() {
  return (
    <a className="link-button" href="/api/export/bibliography" download="bibliography.txt">
      <Download size={14} /> Export bibliography
    </a>
  );
}
