import { useState } from "react";
import { FileSearch, RefreshCcw, Save } from "lucide-react";
import { api, type SourceDiscoveryResponse, type SourceDiscoveryResult } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";
import { useWorkspaceData } from "../data";

type DiscoveryState =
  | { status: "empty"; payload: null; error: null }
  | { status: "loading"; payload: null; error: null }
  | { status: "ready"; payload: SourceDiscoveryResponse; error: null }
  | { status: "failure"; payload: SourceDiscoveryResponse | null; error: Error };

export function SourceDiscoveryPanel({ announce }: PanelComponentProps) {
  const { objects } = useWorkspaceData();
  const [query, setQuery] = useState("");
  const [offlineOnly, setOfflineOnly] = useState(false);
  const [apisEnabled, setApisEnabled] = useState(true);
  const [state, setState] = useState<DiscoveryState>({ status: "empty", payload: null, error: null });
  const [savingId, setSavingId] = useState<string | null>(null);

  async function runSearch() {
    if (!query.trim()) return;
    setState({ status: "loading", payload: null, error: null });
    try {
      const payload = await api.post<SourceDiscoveryResponse>("/api/sources/discovery/search", {
        query,
        project_id: "default",
        offline_only: offlineOnly,
        scholarly_apis_enabled: apisEnabled,
      });
      setState({ status: "ready", payload, error: null });
    } catch (error) {
      setState({ status: "failure", payload: null, error: error instanceof Error ? error : new Error(String(error)) });
    }
  }

  async function saveResult(result: SourceDiscoveryResult) {
    setSavingId(resultKey(result));
    try {
      await api.post("/api/sources/save", {
        project_id: "default",
        query,
        result,
        user_initiated: true,
        source_origin: "discovery",
        save_pdf: false,
        automatic_pdf_download: false,
        allowed_pdf_domains: [],
      });
      announce(`Saved source ${result.title}`);
      objects.reload();
    } finally {
      setSavingId(null);
    }
  }

  return (
    <PanelScaffold title="Source Discovery">
      <form
        className="panel-toolbar search-toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          void runSearch();
        }}
      >
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search papers and metadata providers" aria-label="Paper search" />
        <button type="submit">
          <FileSearch size={14} /> Search
        </button>
      </form>
      <div className="toggle-row">
        <label>
          <input type="checkbox" checked={offlineOnly} onChange={(event) => setOfflineOnly(event.target.checked)} />
          Offline/cache only
        </label>
        <label>
          <input type="checkbox" checked={apisEnabled} onChange={(event) => setApisEnabled(event.target.checked)} />
          Scholarly APIs
        </label>
      </div>

      {state.status === "empty" && <EmptyState title="No query run" message="Search for papers across configured scholarly providers." action="Search for papers" onAction={() => void runSearch()} />}
      {state.status === "loading" && <LoadingState title="Searching providers" />}
      {state.status === "failure" && <FailureState error={state.error} onRetry={runSearch} />}
      {state.status === "ready" && (
        <>
          <div className={`provider-summary ${state.payload.state}`} role="status">
            <strong>{state.payload.state}</strong>
            <span>{state.payload.results.length} results</span>
          </div>
          <div className="provider-grid">
            {(state.payload.provider_statuses ?? []).map((provider) => (
              <span key={provider.provider} className={`provider-state ${provider.state.replaceAll(" ", "-")}`}>
                {provider.provider}: {provider.state}
              </span>
            ))}
          </div>
          {state.payload.results.length === 0 ? (
            <EmptyState title="No results" message="Providers returned no matching papers for this query." action="Refine query" onAction={() => undefined} />
          ) : (
            <div className="result-list">
              {state.payload.results.map((result) => (
                <article className="result-row" key={resultKey(result)}>
                  <header>
                    <strong>{result.title}</strong>
                    <span className="status-pill">{Math.round(Number(result.confidence ?? 0) * 100)}%</span>
                  </header>
                  <dl>
                    <div>
                      <dt>Authors</dt>
                      <dd>{Array.isArray(result.authors) ? result.authors.join(", ") : result.authors || "Unknown"}</dd>
                    </div>
                    <div>
                      <dt>Year</dt>
                      <dd>{result.year ?? "n.d."}</dd>
                    </div>
                    <div>
                      <dt>Venue</dt>
                      <dd>{result.venue ?? "Unknown"}</dd>
                    </div>
                    <div>
                      <dt>DOI</dt>
                      <dd>{result.doi ?? "none"}</dd>
                    </div>
                  </dl>
                  <div className="row-actions">
                    <button onClick={() => void saveResult(result)} disabled={savingId === resultKey(result)}>
                      <Save size={13} /> {savingId === resultKey(result) ? "Saving" : "Save"}
                    </button>
                    <button onClick={() => void runSearch()}>
                      <RefreshCcw size={13} /> Refresh
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </PanelScaffold>
  );
}

function resultKey(result: SourceDiscoveryResult) {
  return String(result.id ?? result.doi ?? result.title);
}
