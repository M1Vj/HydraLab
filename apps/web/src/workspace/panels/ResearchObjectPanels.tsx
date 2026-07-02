import { useEffect, useState } from "react";
import { Download, KeyRound, RefreshCcw, ShieldCheck } from "lucide-react";
import { api, type BrowserEventRecord, type SettingsResponse } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { useWorkspaceData } from "../data";
import { EmptyState, FailureState, LoadingState, NotWiredState, PanelScaffold } from "./PanelState";

export function CitationEvidencePanel({ openPanel }: PanelComponentProps) {
  const { objects } = useWorkspaceData();
  if (objects.status === "loading" && !objects.data) return <LoadingState title="Loading evidence graph" />;
  if (objects.status === "failure") return <FailureState error={objects.error} onRetry={objects.reload} />;
  const data = objects.data;
  if (!data || (data.objects.evidence.length === 0 && data.objects.citations.length === 0 && data.objects.claims.length === 0)) {
    return <EmptyState title="No citations" message="Claims, citations and evidence links will appear after sources are saved or imported." action="Add from source library" onAction={() => openPanel("source-discovery")} />;
  }
  return (
    <PanelScaffold title="Citation & Evidence">
      <div className="object-list">
        {data.objects.claims.map((claim) => (
          <article className="object-card" key={claim.id}>
            <strong>{claim.text}</strong>
            <small>{claim.status ?? "needs_review"}</small>
          </article>
        ))}
        {data.objects.evidence.map((evidence) => (
          <article className="object-card" key={evidence.id}>
            <strong>{evidence.support}</strong>
            <span>{evidence.passage}</span>
            <button onClick={() => openPanel("pdf-reader", { sourceId: evidence.source_id, title: evidence.source_title ?? evidence.source_id })}>Go to origin</button>
          </article>
        ))}
        {data.objects.citations.map((citation) => (
          <article className="object-card" key={citation.id}>
            <strong>{citation.citation_key || citation.source_id}</strong>
            <span>{citation.text}</span>
          </article>
        ))}
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

export function SettingsPanel() {
  const { settings } = useWorkspaceData();
  const [saving, setSaving] = useState(false);
  if (settings.status === "loading" && !settings.data) return <LoadingState title="Loading settings" />;
  if (settings.status === "failure") return <FailureState error={settings.error} onRetry={settings.reload} />;
  const payload = settings.data as SettingsResponse | null;
  async function saveProvider(provider: string, model: string) {
    setSaving(true);
    try {
      await api.put("/api/settings/provider", { provider, model, api_key_ref: "keychain:pending-write" });
      settings.reload();
    } finally {
      setSaving(false);
    }
  }
  return (
    <PanelScaffold title="Settings">
      <div className="settings-grid">
        <section className="settings-section">
          <header>
            <ShieldCheck size={15} />
            <strong>Consent and capture</strong>
          </header>
          <label><input type="checkbox" checked={String(payload?.workspace_preferences?.restoreOnLaunch ?? "true") === "true"} readOnly /> Session restore</label>
          <label><input type="checkbox" checked={false} readOnly /> Browser page text to provider</label>
          <label><input type="checkbox" checked={false} readOnly /> Offline-only provider block</label>
        </section>
        <section className="settings-section">
          <header>
            <KeyRound size={15} />
            <strong>Providers</strong>
          </header>
          {(payload?.provider_settings ?? []).length === 0 ? <span>not set</span> : payload?.provider_settings.map((provider) => (
            <div key={provider.provider} className="provider-row">
              <span>{provider.provider}</span>
              <span>{provider.model}</span>
              <span>{provider.api_key_ref || provider.secret_ref ? "stored" : "not set"}</span>
            </div>
          ))}
          <button disabled={saving} onClick={() => void saveProvider("openai", "gpt-4.1")}>Store provider reference</button>
        </section>
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

export function GitPanel() {
  return <NotWiredState title="Git" route="Git HTTP route" />;
}

export function PdfReaderPanel({ config }: PanelComponentProps) {
  const sourceId = typeof config?.sourceId === "string" ? config.sourceId : null;
  return (
    <PanelScaffold title="PDF Reader">
      <EmptyState
        title={sourceId ? "PDF source selected" : "No document open"}
        message={sourceId ? `Annotations are available through /api/annotations/${sourceId}. Local file rendering remains in the PDF module branch.` : "Open a local PDF or select a source from Explorer."}
        action={sourceId ? "Load annotations" : "Open a PDF"}
        onAction={() => undefined}
      />
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
