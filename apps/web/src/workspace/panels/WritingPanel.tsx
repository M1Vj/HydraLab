import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Check, Download, FileUp, RotateCcw, Settings2, ShieldAlert, Wand2, X } from "lucide-react";
import { HydraMarkdownEditor } from "../../components/editor/HydraMarkdownEditor";
import type { InlineSuggestion } from "../../lib/editor/markdown";
import {
  API_BASE_URL,
  HydraApiError,
  applyDocxEditPlan,
  createManuscriptPackage,
  exportManuscript,
  getManuscriptExportPreview,
  getDocxAvailability,
  getDocxEditPlan,
  getFormatDefaults,
  getLatexAvailability,
  getManuscriptFormat,
  listManuscripts,
  reviewDocxOperation,
  rollbackDocxEditPlan,
  type DocxAvailabilityResponse,
  type DocxEditPlanResponse,
  type DocxImportResponse,
  type DocxReviewStatus,
  type LatexAvailabilityResponse,
  type ManuscriptFormat,
  type ManuscriptFormatResponse,
  type ManuscriptPackageResponse,
} from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";
import {
  allowedDocxActions,
  docxActionState,
  exportPreviewState,
  formatRows,
  formatValidationMessage,
  latexCompileState,
  manuscriptPackageBlockers,
} from "./writingFormats";
import {
  approvedOperations,
  canApplyPlan,
  docxPlanUiState,
  isUntrusted,
  operationDiffSummary,
  operationLocationLabel,
  riskBadgeClass,
  summarizeReviewProgress,
} from "./docxEditPlan";

type RelatedWorkSuggestionDetail = {
  text?: string;
  trace_links?: unknown[];
};

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
  const [relatedWorkSuggestion, setRelatedWorkSuggestion] = useState<InlineSuggestion | null>(null);
  const [imported, setImported] = useState<DocxImportResponse | null>(null);
  const [docxNotice, setDocxNotice] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [planId, setPlanId] = useState("");
  const [plan, setPlan] = useState<DocxEditPlanResponse | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planError, setPlanError] = useState<Error | null>(null);
  const [planNotice, setPlanNotice] = useState("");

  const [preview, setPreview] = useState<ManuscriptPackageResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<Error | null>(null);
  const [ackCitationIssues, setAckCitationIssues] = useState(false);
  const [ackRedactions, setAckRedactions] = useState<string[]>([]);
  const [approvalId, setApprovalId] = useState("");
  const [packageNotice, setPackageNotice] = useState("");

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    if (active) {
      void loadFormat(active);
      void loadExportPreview(active);
    }
  }, [active]);

  useEffect(() => {
    if (relatedWorkSuggestion && source.includes("hydralab-trace")) {
      setRelatedWorkSuggestion(null);
    }
  }, [relatedWorkSuggestion, source]);

  useEffect(() => {
    function onRelatedWorkSuggestion(event: Event) {
      const detail = (event as CustomEvent<RelatedWorkSuggestionDetail>).detail;
      stageRelatedWorkSuggestion(detail);
    }
    window.addEventListener("hydra:related-work-suggestion", onRelatedWorkSuggestion);
    return () => window.removeEventListener("hydra:related-work-suggestion", onRelatedWorkSuggestion);
  }, [source]);

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

  async function loadExportPreview(name: string) {
    setPreviewLoading(true);
    setPreviewError(null);
    setPackageNotice("");
    setAckCitationIssues(false);
    setAckRedactions([]);
    try {
      setPreview(await getManuscriptExportPreview(name));
    } catch (caught) {
      setPreview(null);
      setPreviewError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setPreviewLoading(false);
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

  async function loadPlan(id: string) {
    if (!id.trim()) return;
    setPlanLoading(true);
    setPlanError(null);
    setPlanNotice("");
    try {
      setPlan(await getDocxEditPlan(id.trim()));
    } catch (caught) {
      setPlan(null);
      setPlanError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setPlanLoading(false);
    }
  }

  async function onReview(operationId: string, decision: DocxReviewStatus) {
    if (!plan) return;
    try {
      await reviewDocxOperation(plan.plan.id, operationId, decision);
      await loadPlan(plan.plan.id);
      announce(`Operation ${decision}`);
    } catch (caught) {
      setPlanNotice(`Review failed: ${caught instanceof Error ? caught.message : String(caught)}`);
    }
  }

  async function onApplyPlan() {
    if (!plan) return;
    setPlanNotice("");
    try {
      const result = await applyDocxEditPlan(plan.plan.id);
      setPlan(result);
      setPlanNotice("Applied approved operations to a validated copy, then replaced the working DOCX.");
      announce("DOCX edit plan applied");
    } catch (caught) {
      const message = caught instanceof HydraApiError ? caught.message : String(caught);
      setPlanNotice(`Apply failed (original left untouched): ${message}`);
    }
  }

  async function onRollbackPlan() {
    if (!plan) return;
    setPlanNotice("");
    try {
      const result = await rollbackDocxEditPlan(plan.plan.id);
      setPlan(result);
      setPlanNotice("Rolled back to the pre-apply checkpoint (byte-identical original restored).");
      announce("DOCX edit plan rolled back");
    } catch (caught) {
      const message = caught instanceof HydraApiError ? caught.message : String(caught);
      setPlanNotice(`Rollback failed: ${message}`);
    }
  }

  async function onCreatePackage() {
    if (!active) return;
    setPackageNotice("");
    try {
      const result = await createManuscriptPackage(active, {
        approval_id: approvalId.trim() || null,
        targets: ["docx", "latex", "html", "pdf"],
        acknowledge_citation_issues: ackCitationIssues,
        acknowledged_redaction_item_ids: ackRedactions,
      });
      setPreview(result);
      if (result.status === "created") {
        setPackageNotice(`Package created at ${result.package_dir}`);
        announce("Manuscript package created");
      } else if (result.status === "approval_required") {
        setPackageNotice(`Approval required${result.gate?.approval_id ? `: ${result.gate.approval_id}` : ""}`);
      } else if (result.status === "validation_blocked") {
        setPackageNotice("Package blocked by citation validation.");
      } else if (result.status === "redaction_blocked") {
        setPackageNotice("Package blocked by redaction decisions.");
      } else {
        setPackageNotice(`Package status: ${result.status}`);
      }
    } catch (caught) {
      const message = caught instanceof HydraApiError ? caught.message : String(caught);
      setPackageNotice(`Package failed: ${message}`);
    }
  }

  function stageRelatedWorkSuggestion(detail?: RelatedWorkSuggestionDetail) {
    const traceLinks = detail?.trace_links ?? [
      {
        source_id: "saved-source",
        citation_id: "saved-citation",
        locator: { section: "Related Work" },
      },
    ];
    const text = detail?.text ?? "Saved literature grounds this related-work synthesis. [@saved-citation]";
    const insertion =
      `\n\n## Related Work\n\n${text}\n` +
      `<!-- hydralab-trace:${JSON.stringify(traceLinks)} -->\n`;
    setRelatedWorkSuggestion({
      id: "related-work-draft",
      from: source.length,
      to: source.length,
      replacement: insertion,
    });
    announce("Related-work draft staged for inline review");
  }

  const converterState = useMemo(() => docxActionState(docx), [docx]);
  const compileState = useMemo(() => latexCompileState(latex), [latex]);
  const manuscriptPreviewState = useMemo(
    () => exportPreviewState({ active, loading: previewLoading, error: previewError, preview }),
    [active, previewLoading, previewError, preview],
  );
  const packageBlockers = useMemo(
    () => manuscriptPackageBlockers(preview, ackCitationIssues, ackRedactions),
    [preview, ackCitationIssues, ackRedactions],
  );
  const planState = useMemo(
    () => docxPlanUiState({ loading: planLoading, error: planError, plan }),
    [planLoading, planError, plan],
  );
  const planOperations = plan?.operations ?? [];
  const reviewProgress = useMemo(() => summarizeReviewProgress(planOperations), [planOperations]);
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
            suggestions={relatedWorkSuggestion ? [relatedWorkSuggestion] : []}
            onChange={setSource}
            onSave={() => announce("LaTeX source updated (in-memory draft)")}
          />
          <div className="docx-actions" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" onClick={() => stageRelatedWorkSuggestion()} disabled={Boolean(relatedWorkSuggestion)}>
              <Wand2 size={14} aria-hidden /> Stage related work
            </button>
            {relatedWorkSuggestion && <span className="status-pill">inline accept/reject required</span>}
          </div>
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

        <section aria-label="Export package preview">
          <h3>Export package preview</h3>
          {manuscriptPreviewState === "loading" && <LoadingState title="Loading export preview" />}
          {manuscriptPreviewState === "failure" && previewError && (
            <FailureState error={previewError} onRetry={() => active && void loadExportPreview(active)} />
          )}
          {manuscriptPreviewState === "empty" && (
            <EmptyState title="No export preview" message="Select a manuscript with working sources to preview its package." />
          )}
          {manuscriptPreviewState === "ready" && preview && (
            <div className="manuscript-export-preview" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="docx-plan-meta" role="status">
                <span>Template: {preview.document.template_id}</span>
                <span> · Sections: {preview.document.sections.length}</span>
                <span> · Figures: {preview.document.figures.length}</span>
                <span> · Tables: {preview.document.tables.length}</span>
                <span> · Citations: {preview.document.citation_keys.length}</span>
              </div>

              {preview.validation.has_issues ? (
                <div className="panel-state failure" role="alert">
                  <AlertTriangle size={16} aria-hidden />
                  <div>
                    <strong>Citation validation</strong>
                    {preview.validation.unresolved_citation_keys.length > 0 && (
                      <div>Unresolved: {preview.validation.unresolved_citation_keys.join(", ")}</div>
                    )}
                    {preview.validation.missing_metadata.length > 0 && (
                      <div>
                        Missing metadata:{" "}
                        {preview.validation.missing_metadata.map((item) => `${item.citation_key} (${item.missing_fields})`).join(", ")}
                      </div>
                    )}
                    <label>
                      <input
                        type="checkbox"
                        checked={ackCitationIssues}
                        onChange={(event) => setAckCitationIssues(event.target.checked)}
                      />{" "}
                      Acknowledge citation issues
                    </label>
                  </div>
                </div>
              ) : (
                <div className="panel-state" role="status">
                  <Check size={16} aria-hidden /> Citation validation clear
                </div>
              )}

              <div className="redaction-list" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <strong>Redaction decisions</strong>
                {preview.redaction.items.length === 0 ? (
                  <span>No redaction hazards detected.</span>
                ) : (
                  preview.redaction.items.map((item) => (
                    <label key={item.id} className="panel-state failure">
                      <input
                        type="checkbox"
                        checked={ackRedactions.includes(item.id)}
                        onChange={(event) => {
                          setAckRedactions((current) =>
                            event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id),
                          );
                        }}
                      />
                      <span>
                        {item.category}: {item.path} — {item.reason}
                      </span>
                    </label>
                  ))
                )}
              </div>

              <div className="authorship-ledger" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <strong>Authorship ledger</strong>
                {preview.document.authorship_ledger.map((entry) => (
                  <span key={entry.section}>
                    {entry.section}: {entry.authorship}
                  </span>
                ))}
              </div>

              {preview.outputs && Object.keys(preview.outputs).length > 0 && (
                <div className="docx-view" aria-label="Package outputs">
                  <h4>Package outputs</h4>
                  <dl>
                    {Object.values(preview.outputs).map((output) => (
                      <div key={output.target}>
                        <dt>{output.target}</dt>
                        <dd>
                          {output.status}
                          {output.message ? ` · ${output.message}` : ""}
                        </dd>
                      </div>
                    ))}
                  </dl>
                  {preview.manifest_path && <small>Manifest: {preview.manifest_path}</small>}
                </div>
              )}

              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <label>
                  Approval id{" "}
                  <input
                    type="text"
                    value={approvalId}
                    placeholder={preview.gate?.approval_id ?? "pending approval id"}
                    onChange={(event) => setApprovalId(event.target.value)}
                    aria-label="Package approval id"
                  />
                </label>
                <button onClick={() => void onCreatePackage()} disabled={packageBlockers.length > 0}>
                  <Download size={14} aria-hidden /> {approvalId.trim() ? "Create package" : "Request package approval"}
                </button>
                {packageBlockers.length > 0 && <span className="status-pill">blocked: {packageBlockers.join(", ")}</span>}
              </div>
              {packageNotice && (
                <div className="panel-state" role="status">
                  <span>{packageNotice}</span>
                </div>
              )}
            </div>
          )}
        </section>

        <section aria-label="DOCX assisted edits" className="docx-edit-plan">
          <h3>DOCX assisted edits (OpenXML)</h3>
          {/* Phase 2: typed, inspectable structural edits reviewed per-operation
              before any apply. Nothing is applied without explicit approval
              (HL-WRITE-35); document text never triggers an edit (HL-TRUST-30). */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <label>
              Edit plan{" "}
              <input
                type="text"
                aria-label="Edit plan id"
                placeholder="edit-plan id"
                value={planId}
                onChange={(event) => setPlanId(event.target.value)}
              />
            </label>
            <button onClick={() => void loadPlan(planId)} disabled={!planId.trim()}>
              Load plan
            </button>
          </div>

          {planState === "loading" && <LoadingState title="Loading edit plan" />}
          {planState === "permission-denied" && planError && (
            <FailureState error={planError} onRetry={() => void loadPlan(planId)} />
          )}
          {planState === "failure" && planError && (
            <FailureState error={planError} onRetry={() => void loadPlan(planId)} />
          )}
          {planState === "empty" && (
            <EmptyState
              title="No proposed edit plan"
              message="Ask the assistant to propose DOCX edits, then load the plan id here to review each structural operation before applying."
            />
          )}

          {planState === "ready" && plan && (
            <div className="docx-plan-review">
              <div className="docx-plan-meta" role="status">
                <span>
                  Target: {plan.plan.manuscript}/{plan.plan.target_relpath}
                </span>
                <span> · Status: {plan.plan.status}</span>
                <span>
                  {" "}
                  · {reviewProgress.approved} approved / {reviewProgress.rejected} rejected / {reviewProgress.pending}{" "}
                  pending
                </span>
              </div>

              <ul className="docx-op-list" style={{ listStyle: "none", padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
                {planOperations.map((op) => (
                  <li key={op.id} className="docx-op" style={{ border: "1px solid var(--border, #ccc)", borderRadius: 6, padding: 8 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                      <strong>{op.op_type}</strong>
                      <span className={riskBadgeClass(op.risk_label)}>risk: {op.risk_label}</span>
                    </div>
                    <div className="docx-op-location">{operationLocationLabel(op)}</div>
                    <div className="docx-op-diff" title={operationDiffSummary(op)}>
                      {operationDiffSummary(op)}
                    </div>
                    {isUntrusted(op) && (
                      <div className="panel-state failure" role="alert">
                        <ShieldAlert size={14} aria-hidden /> untrusted-external — traces to document content
                        {op.motivating_excerpt ? `: "${op.motivating_excerpt}"` : ""}
                      </div>
                    )}
                    <div className="docx-op-actions" style={{ display: "flex", gap: 8, marginTop: 6 }}>
                      <button
                        onClick={() => void onReview(op.id, "approved")}
                        disabled={op.review_status === "approved"}
                        aria-label={`Approve ${op.op_type} at ${operationLocationLabel(op)}`}
                      >
                        <Check size={14} aria-hidden /> Approve
                      </button>
                      <button
                        onClick={() => void onReview(op.id, "rejected")}
                        disabled={op.review_status === "rejected"}
                        aria-label={`Reject ${op.op_type} at ${operationLocationLabel(op)}`}
                      >
                        <X size={14} aria-hidden /> Reject
                      </button>
                      <span className="docx-op-status">
                        {op.review_status}
                        {op.validation_status === "invalid" && " · invalid"}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>

              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button onClick={() => void onApplyPlan()} disabled={!canApplyPlan(planOperations)}>
                  Apply approved ({approvedOperations(planOperations).length})
                </button>
                <button onClick={() => void onRollbackPlan()} disabled={!plan.plan.checkpoint_ref}>
                  <RotateCcw size={14} aria-hidden /> Roll back
                </button>
              </div>
            </div>
          )}

          {planNotice && (
            <div className="panel-state" role="status">
              <span>{planNotice}</span>
            </div>
          )}
        </section>
      </div>
    </PanelScaffold>
  );
}
