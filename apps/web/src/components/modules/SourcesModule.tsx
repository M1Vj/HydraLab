import React, { useMemo, useState } from "react";
import { FileSearch, Pause, RefreshCcw, Save, XCircle } from "lucide-react";
import { useAppContext } from "../../core/context";
import { registry } from "../../core/registry";
import {
  cacheAgeLabel,
  DEFAULT_SOURCE_DISCOVERY_SETTINGS,
  discoveryResultFields,
  pdfDownloadCopy,
  resolveDiscoveryPanelState,
  sourceDiscoveryNetworkPosture,
  type DiscoveryProviderStatus,
  type DiscoveryResultRow,
  type SourceDiscoverySettings,
} from "../../lib/hydra";

const providerNames = ["openalex", "arxiv", "crossref", "unpaywall", "semantic_scholar", "core", "opencitations"];

const sampleResults: DiscoveryResultRow[] = [
  {
    id: "disc_attention",
    title: "Attention Is All You Need",
    authors: ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
    year: 2017,
    venue: "NeurIPS",
    doi: "10.48550/arXiv.1706.03762",
    pdfAvailable: true,
    provider: "openalex",
    expectedSizeBytes: 4 * 1024 * 1024,
    confidence: 0.94,
    duplicateState: "exact-merged",
    cacheAgeSeconds: 84,
  },
  {
    id: "disc_transformer_survey",
    title: "A Survey of Transformers",
    authors: ["Research Author"],
    year: 2021,
    venue: "ACM Computing Surveys",
    doi: null,
    pdfAvailable: false,
    provider: "semantic_scholar",
    expectedSizeBytes: null,
    confidence: 0.72,
    duplicateState: "possible-duplicate",
    cacheAgeSeconds: 3600,
  },
];

export function SourceDiscoveryPanel() {
  const [query, setQuery] = useState("");
  const [settings, setSettings] = useState<SourceDiscoverySettings>(DEFAULT_SOURCE_DISCOVERY_SETTINGS);
  const [providerStatuses, setProviderStatuses] = useState<DiscoveryProviderStatus[]>(providerNames.map((provider) => ({ provider, state: "idle" })));
  const [results, setResults] = useState<DiscoveryResultRow[]>([]);
  const [savedIds, setSavedIds] = useState<string[]>([]);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);
  const [autoDownloadPaused, setAutoDownloadPaused] = useState(false);

  const panelState = resolveDiscoveryPanelState({
    query,
    providerStatuses,
    results,
    offlineOnly: settings.offlineOnly,
    scholarlyApisEnabled: settings.scholarlyApisEnabled,
  });
  const posture = sourceDiscoveryNetworkPosture(settings);

  function runSearch() {
    if (!query.trim()) return;
    if (!posture.providerCallsAllowed) {
      setProviderStatuses(providerNames.map((provider) => ({ provider, state: "offline" })));
      setResults(sampleResults.slice(0, 1).map((row) => ({ ...row, provider: "local-cache", cacheAgeSeconds: 7200 })));
      return;
    }
    setProviderStatuses(providerNames.map((provider) => ({ provider, state: "loading" })));
    setResults([]);
    window.setTimeout(() => {
      setProviderStatuses([
        { provider: "openalex", state: "ready", count: 1 },
        { provider: "arxiv", state: "cache-hit", count: 1, cacheAgeSeconds: 84 },
        { provider: "crossref", state: "ready", count: 1 },
        { provider: "unpaywall", state: "ready", count: 1 },
        { provider: "semantic_scholar", state: "provider rate-limited" },
        { provider: "core", state: "error" },
        { provider: "opencitations", state: "ready", count: 1 },
      ]);
      setResults(sampleResults);
    }, 150);
  }

  function refreshMetadata(row: DiscoveryResultRow) {
    setRefreshingId(row.id);
    window.setTimeout(() => {
      setResults((current) => current.map((item) => (item.id === row.id ? { ...item, cacheAgeSeconds: 0 } : item)));
      setRefreshingId(null);
    }, 150);
  }

  return (
    <div className="source-discovery-panel" aria-label="Source Discovery">
      <form
        className="source-search-row"
        onSubmit={(event) => {
          event.preventDefault();
          runSearch();
        }}
      >
        <label className="ui-field">
          <span>Paper search</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Attention Is All You Need" />
        </label>
        <button type="submit">
          <FileSearch size={14} /> Search
        </button>
      </form>

      <div className="discovery-settings" aria-label="Source discovery network settings">
        <label>
          <input
            type="checkbox"
            checked={settings.offlineOnly}
            onChange={(event) => setSettings((current) => ({ ...current, offlineOnly: event.target.checked }))}
          />
          Offline-only
        </label>
        <label>
          <input
            type="checkbox"
            checked={settings.scholarlyApisEnabled}
            onChange={(event) => setSettings((current) => ({ ...current, scholarlyApisEnabled: event.target.checked }))}
          />
          Scholarly APIs
        </label>
        <label>
          <input
            type="checkbox"
            checked={settings.automaticPdfDownload}
            onChange={(event) => setSettings((current) => ({ ...current, automaticPdfDownload: event.target.checked }))}
          />
          Auto PDF
        </label>
      </div>

      <div className={`discovery-state ${panelState}`} role="status">
        <strong>{panelState}</strong>
        <span>{posture.message}</span>
      </div>

      <div className="provider-grid" aria-label="Per-provider progress">
        {providerStatuses.map((status) => (
          <span key={status.provider} className={`provider-state ${status.state.replaceAll(" ", "-")}`}>
            {status.provider}: {status.state}
          </span>
        ))}
      </div>

      {panelState === "empty" && (
        <div className="empty-panel">
          <p>No query run</p>
          <small>Search fans out to OpenAlex, arXiv, Crossref, Unpaywall, Semantic Scholar, CORE and OpenCitations.</small>
        </div>
      )}

      {panelState === "loading" && (
        <div className="panel-body" aria-busy="true">
          <div className="skeleton" />
          <div className="skeleton short" />
        </div>
      )}

      {panelState === "failure" && (
        <div className="inline-state failure" role="alert">
          <strong>All providers failed</strong>
          <span>HydraLab keeps the error visible and does not silently fail.</span>
          <button onClick={runSearch}>Retry</button>
        </div>
      )}

      {results.length > 0 && (
        <div className="discovery-results" aria-label="Ranked discovery results">
          {results.map((row) => (
            <DiscoveryResultCard
              key={row.id}
              row={row}
              settings={settings}
              saved={savedIds.includes(row.id)}
              refreshing={refreshingId === row.id}
              autoDownloadPaused={autoDownloadPaused}
              onSave={() => setSavedIds((current) => (current.includes(row.id) ? current : [...current, row.id]))}
              onRefresh={() => refreshMetadata(row)}
              onPauseAutoDownload={() => setAutoDownloadPaused(true)}
              onCancelAutoDownload={() => setSettings((current) => ({ ...current, automaticPdfDownload: false }))}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function DiscoveryResultCard({
  row,
  settings,
  saved,
  refreshing,
  autoDownloadPaused,
  onSave,
  onRefresh,
  onPauseAutoDownload,
  onCancelAutoDownload,
}: {
  row: DiscoveryResultRow;
  settings: SourceDiscoverySettings;
  saved: boolean;
  refreshing: boolean;
  autoDownloadPaused: boolean;
  onSave: () => void;
  onRefresh: () => void;
  onPauseAutoDownload: () => void;
  onCancelAutoDownload: () => void;
}) {
  const fields = useMemo(() => discoveryResultFields(row), [row]);
  const pdfCopy = pdfDownloadCopy({
    pdfAvailable: row.pdfAvailable,
    expectedSizeBytes: row.expectedSizeBytes,
    automaticPdfDownload: settings.automaticPdfDownload && !autoDownloadPaused,
    thresholdBytes: settings.largeFileThresholdBytes,
  });

  return (
    <article className="discovery-card">
      <header>
        <strong>{fields.title}</strong>
        <span className="status-pill indexed">{Math.round(row.confidence * 100)}%</span>
      </header>
      <dl>
        <div>
          <dt>Authors</dt>
          <dd>{fields.authors}</dd>
        </div>
        <div>
          <dt>Year</dt>
          <dd>{fields.year}</dd>
        </div>
        <div>
          <dt>Venue</dt>
          <dd>{fields.venue}</dd>
        </div>
        <div>
          <dt>DOI</dt>
          <dd>{fields.doi}</dd>
        </div>
        <div>
          <dt>PDF</dt>
          <dd>
            {fields.pdf} · {fields.expectedSize}
          </dd>
        </div>
        <div>
          <dt>Provider</dt>
          <dd>{fields.provider}</dd>
        </div>
      </dl>
      <p className="helper-text">
        {pdfCopy}. Cache age: {cacheAgeLabel(row.cacheAgeSeconds)}. Duplicate state: {row.duplicateState ?? "unique"}.
      </p>
      <div className="row-actions">
        <button onClick={onSave} disabled={saved}>
          <Save size={13} /> {saved ? "Saved" : "Save to source library"}
        </button>
        <button onClick={onRefresh} disabled={refreshing}>
          <RefreshCcw size={13} /> {refreshing ? "Refreshing" : "Refresh metadata"}
        </button>
        {settings.automaticPdfDownload && (
          <>
            <button onClick={onPauseAutoDownload} disabled={autoDownloadPaused}>
              <Pause size={13} /> Pause auto PDF
            </button>
            <button onClick={onCancelAutoDownload}>
              <XCircle size={13} /> Cancel auto PDF
            </button>
          </>
        )}
      </div>
    </article>
  );
}

export function SourcesSidebar() {
  const { sources } = useAppContext();

  if (sources.length === 0) {
    return (
      <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
        <p>No sources uploaded.</p>
      </div>
    );
  }

  return (
    <div style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
      {sources.map(s => (
        <div 
          key={s.id} 
          style={{ 
            padding: "10px", 
            backgroundColor: "var(--bg-dark)", 
            borderRadius: "6px", 
            border: "1px solid var(--border)" 
          }}
        >
          <div style={{ fontWeight: "bold", fontSize: "13px", color: "var(--fg)" }}>{s.title}</div>
          {s.authors && <div style={{ fontSize: "11px", color: "var(--fg-dim)", marginTop: "4px" }}>{s.authors}</div>}
        </div>
      ))}
    </div>
  );
}

// Register components
registry.register("hydra.sources", SourcesSidebar);
