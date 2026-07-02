import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, FileUp, FilePlus2, Highlighter, Link2, MessageSquareQuote, Minus, Plus, RotateCcw } from "lucide-react";
import * as pdfjsLib from "pdfjs-dist";
import pdfWorker from "pdfjs-dist/build/pdf.worker.mjs?url";
import type { PanelComponentProps } from "../panelRegistry";
import { EmptyState, FailureState, PanelScaffold } from "./PanelState";
import { addHighlight, clampPage, clampScale, loadSourceAnnotations, PdfLifecycle, suggestClaim } from "./pdfController";
import { annotationDraftFromSelection, viewportRectFromQuad, type PdfAnnotationRecord } from "../../lib/annotations/store";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorker;

type ReaderState = "empty" | "loading" | "ready" | "failure";
const DEFAULT_PAGE_SIZE = { width: 612, height: 792 };

export function PdfReaderPanel({ config, announce }: PanelComponentProps) {
  const sourceId = typeof config?.sourceId === "string" ? config.sourceId : null;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const lifecycle = useRef(new PdfLifecycle());

  const [readerState, setReaderState] = useState<ReaderState>("empty");
  const [error, setError] = useState<Error | null>(null);
  const [documentTitle, setDocumentTitle] = useState("");
  const [documentProxy, setDocumentProxy] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [scale, setScale] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [annotations, setAnnotations] = useState<PdfAnnotationRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [autoCreateClaim, setAutoCreateClaim] = useState(false);
  const [annotationError, setAnnotationError] = useState<string>("");

  const selectedAnnotation = useMemo(
    () => annotations.find((annotation) => annotation.sidecar_record_id === selectedId) ?? null,
    [annotations, selectedId],
  );

  // Destroy the pdf.js document + any in-flight render task on unmount (memory safety).
  useEffect(() => {
    const owner = lifecycle.current;
    return () => owner.destroy();
  }, []);

  // Load sidecar annotations when opened via a source ("go to origin").
  useEffect(() => {
    if (!sourceId) {
      setAnnotations([]);
      return;
    }
    let active = true;
    loadSourceAnnotations(sourceId)
      .then((records) => {
        if (active) setAnnotations(records);
      })
      .catch(() => {
        if (active) setAnnotations([]);
      });
    return () => {
      active = false;
    };
  }, [sourceId]);

  // Lazily render only the active page; never mount every page for large documents.
  useEffect(() => {
    const owner = lifecycle.current;
    if (!documentProxy || !canvasRef.current) return;
    let disposed = false;
    setReaderState("loading");
    void documentProxy
      .getPage(page)
      .then(async (pdfPage) => {
        if (disposed || !canvasRef.current) return;
        const viewport = pdfPage.getViewport({ scale });
        setPageSize({ width: viewport.width / scale, height: viewport.height / scale });
        const canvas = canvasRef.current;
        const context = canvas.getContext("2d");
        if (!context) throw new Error("Canvas is unavailable");
        canvas.width = Math.round(viewport.width);
        canvas.height = Math.round(viewport.height);
        canvas.style.width = `${Math.round(viewport.width)}px`;
        canvas.style.height = `${Math.round(viewport.height)}px`;
        const renderTask = pdfPage.render({ canvas, canvasContext: context, viewport });
        owner.trackRender(renderTask);
        await renderTask.promise;
        if (!disposed) setReaderState("ready");
      })
      .catch((reason: unknown) => {
        if (disposed || (reason as { name?: string })?.name === "RenderingCancelledException") return;
        setReaderState("failure");
        setError(reason instanceof Error ? reason : new Error("Unable to render PDF page"));
      });
    return () => {
      disposed = true;
      owner.cancelRender();
    };
  }, [documentProxy, page, scale]);

  async function openPdf(file: File) {
    if (file.type && file.type !== "application/pdf") {
      setReaderState("failure");
      setError(new Error("Only local PDF files are accepted by this reader."));
      return;
    }
    setReaderState("loading");
    setError(null);
    setDocumentTitle(file.name);
    try {
      const data = new Uint8Array(await file.arrayBuffer());
      // The loading task owns the worker transport; destroying it aborts network
      // work and releases the document (PDFDocumentProxy has no destroy of its own).
      const loadingTask = pdfjsLib.getDocument({ data });
      const loaded = await loadingTask.promise;
      lifecycle.current.setDocument(loadingTask);
      setDocumentProxy(loaded);
      setPage(1);
      setPageCount(loaded.numPages);
      announce(`Opened ${file.name}`);
    } catch (reason) {
      setReaderState("failure");
      setError(reason instanceof Error ? reason : new Error("Unable to open PDF"));
    }
  }

  async function createHighlight() {
    if (!sourceId) {
      setAnnotationError("Highlights are saved once a PDF is opened from a source.");
      return;
    }
    setAnnotationError("");
    const selection = window.getSelection()?.toString() ?? "";
    const draft = annotationDraftFromSelection({
      page,
      text: selection,
      rect: { left: 92, top: 112, width: 260, height: 24 },
      pageWidth: pageSize.width,
      pageHeight: pageSize.height,
    });
    try {
      const created = await addHighlight(sourceId, draft);
      setAnnotations((current) => [...current, created]);
      setSelectedId(created.sidecar_record_id);
      announce("Highlight saved");
    } catch (reason) {
      setAnnotationError(reason instanceof Error ? reason.message : "Unable to save highlight");
    }
  }

  async function routeClaimAction() {
    if (!selectedAnnotation) return;
    setAnnotationError("");
    try {
      await suggestClaim(selectedAnnotation.sidecar_record_id, autoCreateClaim);
      announce(autoCreateClaim ? "Draft claim created" : "Claim suggested for review");
    } catch (reason) {
      setAnnotationError(reason instanceof Error ? reason.message : "Unable to route claim action");
    }
  }

  const pageAnnotations = annotations.filter((annotation) => annotation.page === page);

  return (
    <PanelScaffold title="PDF Reader">
      <section className="pdf-reader-module" aria-label="PDF reader">
        <input
          ref={fileInputRef}
          className="sr-only"
          type="file"
          accept="application/pdf,.pdf"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void openPdf(file);
          }}
        />
        <header className="pdf-toolbar">
          <button onClick={() => fileInputRef.current?.click()}>
            <FileUp size={14} /> Open
          </button>
          <button disabled={!documentProxy || page <= 1} onClick={() => setPage((current) => clampPage(current - 1, pageCount))} aria-label="Previous page">
            <ChevronLeft size={14} />
          </button>
          <span className="pdf-page-count">{documentProxy ? `${page} / ${pageCount}` : "0 / 0"}</span>
          <button disabled={!documentProxy || page >= pageCount} onClick={() => setPage((current) => clampPage(current + 1, pageCount))} aria-label="Next page">
            <ChevronRight size={14} />
          </button>
          <button disabled={!documentProxy} onClick={() => setScale((current) => clampScale(current - 0.1))} aria-label="Zoom out">
            <Minus size={14} />
          </button>
          <button disabled={!documentProxy} onClick={() => setScale((current) => clampScale(current + 0.1))} aria-label="Zoom in">
            <Plus size={14} />
          </button>
          <button disabled={!documentProxy} onClick={() => setScale(1)} aria-label="Reset zoom">
            <RotateCcw size={14} />
          </button>
          <button disabled={!documentProxy} onClick={() => void createHighlight()}>
            <Highlighter size={14} /> Highlight
          </button>
        </header>

        <div className="pdf-reader-grid">
          <div className="pdf-stage" data-state={readerState}>
            {readerState === "empty" && !documentProxy && (
              <EmptyState
                title={sourceId ? "Source ready" : "No document open"}
                message={sourceId ? "Open the source PDF to read it with its saved annotations." : "Open a local PDF or select a source from Explorer."}
                action="Open a PDF"
                onAction={() => fileInputRef.current?.click()}
              />
            )}
            {readerState === "loading" && <div className="skeleton-line pdf-skeleton" aria-busy="true" />}
            {readerState === "failure" && error && (
              <FailureState error={error} onRetry={() => fileInputRef.current?.click()} />
            )}
            <div className={`pdf-page-host ${documentProxy ? "ready" : ""}`} aria-label={documentTitle || "PDF page"}>
              <canvas ref={canvasRef} />
              {documentProxy && (
                <div className="pdf-annotation-layer" aria-label="PDF annotations">
                  {pageAnnotations.map((annotation) => {
                    const rect = viewportRectFromQuad(annotation.quad_points, pageSize.width, pageSize.height, scale);
                    return (
                      <button
                        key={annotation.sidecar_record_id}
                        className={`pdf-annotation-mark ${selectedId === annotation.sidecar_record_id ? "selected" : ""}`}
                        style={{ left: rect.left, top: rect.top, width: rect.width, height: Math.max(rect.height, 10) }}
                        title={annotation.text}
                        aria-label={`Annotation: ${annotation.text}`}
                        onClick={() => setSelectedId(annotation.sidecar_record_id)}
                      />
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          <aside className="annotation-inspector" aria-label="Annotation inspector">
            <header>
              <MessageSquareQuote size={15} />
              <strong>Annotation</strong>
            </header>
            {selectedAnnotation ? (
              <>
                <p>{selectedAnnotation.text}</p>
                <dl>
                  <div>
                    <dt>Page</dt>
                    <dd>{selectedAnnotation.page}</dd>
                  </div>
                  <div>
                    <dt>Revision</dt>
                    <dd>{selectedAnnotation.rev}</dd>
                  </div>
                  <div>
                    <dt>Links</dt>
                    <dd>{selectedAnnotation.linked_claim_ids.length + selectedAnnotation.linked_note_ids.length}</dd>
                  </div>
                </dl>
                <label className="inspector-toggle">
                  <input type="checkbox" checked={autoCreateClaim} onChange={(event) => setAutoCreateClaim(event.target.checked)} />
                  Auto-create draft claims
                </label>
                <button onClick={() => void routeClaimAction()}>
                  {autoCreateClaim ? <FilePlus2 size={13} /> : <Link2 size={13} />}
                  {autoCreateClaim ? "Draft claim" : "Suggest claim"}
                </button>
              </>
            ) : (
              <div className="panel-state empty" role="status">
                <span>No annotation selected</span>
              </div>
            )}
            {annotationError && <p className="inspector-error" role="alert">{annotationError}</p>}
          </aside>
        </div>
      </section>
    </PanelScaffold>
  );
}
