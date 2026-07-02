import { useEffect, useState } from "react";
import { Download, FileArchive } from "lucide-react";
import { api, API_BASE_URL, type ExportOptionsResponse } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";
import { DEFAULT_INCLUSION, docxSetupRequired, type ExportInclusion } from "./exportController";

const CATEGORY_LABELS: Record<keyof ExportInclusion, string> = {
  include_chats: "Chats",
  include_agent_logs: "Agent logs",
  include_browser_snapshots: "Browser snapshots",
  include_annotations: "Annotations",
};

export function ExportPanel({ announce }: PanelComponentProps) {
  const [options, setOptions] = useState<ExportOptionsResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [inclusion, setInclusion] = useState<ExportInclusion>(DEFAULT_INCLUSION);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setError(null);
    try {
      setOptions(await api.get<ExportOptionsResponse>("/api/export/options"));
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  async function exportZip() {
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE_URL}/export/project-zip`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ selected_files: null, ...inclusion }),
      });
      const blob = await response.blob();
      triggerDownload(blob, "hydralab_project.zip");
      announce("Exported clean project ZIP");
    } finally {
      setBusy(false);
    }
  }

  async function exportCitations(format: string) {
    const response = await fetch(`${API_BASE_URL}/export/citations`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source_ids: [], format }),
    });
    const text = await response.text();
    triggerDownload(new Blob([text]), `citations.${format === "csl" ? "json" : format}`);
    announce(`Exported citations as ${format}`);
  }

  if (error) return <FailureState error={error} onRetry={load} />;
  if (!options) return <LoadingState title="Loading export options" />;
  if (options.bundle_formats.length === 0) return <EmptyState title="No export formats" message="Export formats are unavailable." />;

  return (
    <PanelScaffold title="Exports">
      <section className="settings-section">
        <header>
          <Download size={15} />
          <strong>Citations</strong>
        </header>
        <div className="export-format-row">
          {options.citation_formats.map((format) => (
            <button key={format} onClick={() => void exportCitations(format)}>
              {format.toUpperCase()}
            </button>
          ))}
        </div>
      </section>

      <section className="settings-section">
        <header>
          <FileArchive size={15} />
          <strong>Bundles</strong>
        </header>
        <p className="settings-hint">Excludes {options.excluded_by_default.join(", ")} by default.</p>
        <fieldset className="export-includes">
          <legend>Optional include</legend>
          {(Object.keys(CATEGORY_LABELS) as Array<keyof ExportInclusion>).map((key) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={inclusion[key]}
                onChange={(event) => setInclusion((current) => ({ ...current, [key]: event.target.checked }))}
              />
              {CATEGORY_LABELS[key]}
            </label>
          ))}
        </fieldset>
        <div className="export-format-row">
          {options.bundle_formats.map((format) => (
            <button
              key={format.id}
              disabled={!format.available || busy}
              title={format.available ? undefined : format.message}
              onClick={() => (format.id === "project-zip" ? void exportZip() : undefined)}
            >
              {format.label}
              {!format.available && <span className="setup-required"> — {format.state}</span>}
            </button>
          ))}
        </div>
        {docxSetupRequired(options) && (
          <p className="settings-hint" role="note">
            DOCX export shows a setup-required state until the writing branch registers an exporter.
          </p>
        )}
      </section>
    </PanelScaffold>
  );
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
