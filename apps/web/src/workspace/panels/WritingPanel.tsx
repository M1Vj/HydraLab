import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Download, FileUp, Settings2, Wand2 } from "lucide-react";
import { HydraMarkdownEditor } from "../../components/editor/HydraMarkdownEditor";
import {
  API_BASE_URL,
  HydraApiError,
  exportManuscript,
  getDocxAvailability,
  getFormatDefaults,
  getLatexAvailability,
  getManuscriptFormat,
  listManuscripts,
  type DocxAvailabilityResponse,
  type DocxImportResponse,
  type LatexAvailabilityResponse,
  type ManuscriptFormat,
  type ManuscriptFormatResponse,
} from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";
import {
  allowedDocxActions,
  docxActionState,
  formatRows,
  formatValidationMessage,
  latexCompileState,
} from "./writingFormats";

export function WritingPanel({ announce }: PanelComponentProps) {
  const [manuscripts, setManuscripts] = useState<string[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [defaults, setDefaults] = useState<ManuscriptFormat | null>(null);
  const [formatResponse, setFormatResponse] = useState<ManuscriptFormatResponse | null>(null);
  const [docx, setDocx] = useState<DocxAvailabilityResponse | null>(null);
  const [latex, setLatex] = useState<LatexAvailabilityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const [source, setSource] = useState("\\documentclass{article}\n\\begin{document}\nDraft\n\\end{document}\n");
  const [imported, setImported] = useState<DocxImportResponse | null>(null);
  const [docxNotice, setDocxNotice] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    if (active) void loadFormat(active);
  }, [active]);

  async function bootstrap() {
    setLoading(true);
    setError(null);
    try {
      const [ms, def, dx, tex] = await Promise.all([
        listManuscripts(),
        getFormatDefaults(),
        getDocxAvailability(),
        getLatexAvailability(),
      ]);
      setManuscripts(ms.manuscripts);
      setDefaults(def.defaults);
      setDocx(dx);
      setLatex(tex);
      if (ms.manuscripts.length > 0) setActive(ms.manuscripts[0]);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setLoading(false);
    }
  }

  async function loadFormat(name: string) {
    try {
      setFormatResponse(await getManuscriptFormat(name));
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  async function onExport() {
    if (!active) return;
    setDocxNotice("");
    try {
      const result = await exportManuscript(active, { source_file: "main.md", include_bibliography: true });
      setDocxNotice(`Exported to ${result.output_path}`);
      announce("Manuscript exported to DOCX");
    } catch (caught) {
      const message = caught instanceof HydraApiError ? caught.message : String(caught);
      setDocxNotice(`Export failed: ${message}`);
    }
  }

  async function onImportFile(file: File) {
    setDocxNotice("");
    setImported(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`${API_BASE_URL}/writing/docx/import`, { method: "POST", body });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ detail: response.statusText }));
        const detail = typeof payload.detail === "object" ? payload.detail.message : payload.detail;
        setDocxNotice(`Import failed: ${detail}`);
        return;
      }
      const result = (await response.json()) as DocxImportResponse;
      setImported(result);
      announce("Imported DOCX");
    } catch (caught) {
      setDocxNotice(`Import failed: ${caught instanceof Error ? caught.message : String(caught)}`);
    }
  }

  const converterState = useMemo(() => docxActionState(docx), [docx]);
  const compileState = useMemo(() => latexCompileState(latex), [latex]);
  const rows = useMemo(
    () => (formatResponse ? formatRows(formatResponse.format, defaults) : []),
    [formatResponse, defaults],
  );
  const validation = formatValidationMessage(formatResponse);

  if (loading) return <LoadingState title="Loading writing formats" />;
  if (error) {
    const apiError = error as HydraApiError;
    if (apiError.kind === "permission-denied" || apiError.kind === "consent-required") {
      return <FailureState error={apiError} onRetry={bootstrap} />;
    }
    return <FailureState error={error} onRetry={bootstrap} />;
  }

  return (
    <PanelScaffold title="Writing & Formats">
      <div className="writing-panel" style={{ display: "flex", flexDirection: "column", gap: 16, padding: 12, overflow: "auto" }}>
        <header className="document-header">
          <strong><Settings2 size={14} aria-hidden /> Writing & Formats</strong>
          <label>
            Manuscript{" "}
            <select
              aria-label="Manuscript"
              value={active ?? ""}
              onChange={(event) => setActive(event.target.value || null)}
              disabled={manuscripts.length === 0}
            >
              {manuscripts.length === 0 && <option value="">No manuscripts</option>}
              {manuscripts.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </header>

        <section aria-label="Effective format">
          <h3>Effective format</h3>
          {validation && (
            <div className="panel-state failure" role="alert">
              <AlertTriangle size={16} aria-hidden /> <span>{validation}</span>
            </div>
          )}
          {!active ? (
            <EmptyState
              title="No manuscript selected"
              message="Create a manuscript under writing/manuscripts/<name>/ with a paper.yaml to define its format."
            />
          ) : (
            <table className="format-table">
              <tbody>
                {rows.map((row) => (
                  <tr key={row.label}>
                    <th scope="row">{row.label}</th>
                    <td>
                      {row.value}
                      {row.overridden && <span className="badge" title="Overridden by paper.yaml"> override</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {formatResponse && <small>Resolved from: {formatResponse.source}</small>}
        </section>

        <section aria-label="LaTeX editing">
          <h3>LaTeX source</h3>
          <HydraMarkdownEditor
            fileRef={`manuscript-latex-${active ?? "draft"}`}
            value={source}
            notes={[]}
            citations={[]}
            onChange={setSource}
            onSave={() => announce("LaTeX source updated (in-memory draft)")}
          />
          {compileState.kind === "setup" ? (
            <div className="panel-state not-wired" role="status">
              <Wand2 size={16} aria-hidden /> <strong>Compile unavailable</strong>
              <span>{compileState.message}</span>
              <button disabled aria-disabled>
                Compile / Preview
              </button>
            </div>
          ) : (
            <button onClick={() => announce(`LaTeX compile via ${compileState.toolchain} (staged)`)}>
              Compile / Preview ({compileState.toolchain})
            </button>
          )}
        </section>

        <section aria-label="DOCX import view export">
          <h3>DOCX (import · view · export)</h3>
          {/* Phase 1 offers only import/view/export; no native paragraph/run/style edit controls (HL-WRITE-21). */}
          {converterState.kind === "setup" ? (
            <div className="panel-state not-wired" role="status">
              <strong>DOCX converter not available</strong>
              <span>{converterState.message}</span>
              <button disabled aria-disabled>
                Export to DOCX
              </button>
            </div>
          ) : (
            <div className="docx-actions" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <small>
                Converter: {converterState.adapter} {converterState.version}
              </small>
              <div style={{ display: "flex", gap: 8 }}>
                {allowedDocxActions().includes("import") && (
                  <>
                    <button onClick={() => fileInputRef.current?.click()}>
                      <FileUp size={14} aria-hidden /> Import DOCX
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".docx"
                      aria-label="Import DOCX file"
                      style={{ display: "none" }}
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) void onImportFile(file);
                        event.target.value = "";
                      }}
                    />
                  </>
                )}
                {allowedDocxActions().includes("export") && (
                  <button onClick={() => void onExport()} disabled={!active}>
                    <Download size={14} aria-hidden /> Export to DOCX
                  </button>
                )}
              </div>
            </div>
          )}
          {docxNotice && (
            <div className="panel-state" role="status">
              <span>{docxNotice}</span>
            </div>
          )}
          {imported && (
            <div className="docx-view" aria-label="Imported DOCX view">
              <h4>Imported: {imported.metadata.title ?? "(untitled)"}</h4>
              <dl>
                {Object.entries(imported.metadata).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
              {imported.flagged_active_content.length > 0 && (
                <div className="panel-state failure" role="alert">
                  <AlertTriangle size={16} aria-hidden />
                  <span>Skipped active content (not executed): {imported.flagged_active_content.join(", ")}</span>
                </div>
              )}
              <pre className="docx-content" style={{ whiteSpace: "pre-wrap", maxHeight: 240, overflow: "auto" }}>
                {imported.content}
              </pre>
            </div>
          )}
        </section>
      </div>
    </PanelScaffold>
  );
}
