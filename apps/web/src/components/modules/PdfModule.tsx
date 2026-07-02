import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, FileUp, Highlighter, Minus, Plus, RotateCcw } from "lucide-react";
import * as pdfjsLib from "pdfjs-dist";
import pdfWorker from "pdfjs-dist/build/pdf.worker.mjs?url";

import { AnnotationInspector } from "./pdf/AnnotationInspector";
import { AnnotationLayer } from "./pdf/AnnotationLayer";
import {
  annotationDraftFromSelection,
  createAnnotation,
  createClaimFromAnnotation,
  listAnnotations,
  type PdfAnnotationRecord,
} from "../../lib/annotations/store";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorker;

type ReaderState = "empty" | "loading" | "ready" | "failure" | "permission-denied";

const SOURCE_ID = "src_attention";
const DEFAULT_PAGE_WIDTH = 612;
const DEFAULT_PAGE_HEIGHT = 792;

export function PdfModule() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);
  const [readerState, setReaderState] = useState<ReaderState>("empty");
  const [error, setError] = useState("");
  const [documentTitle, setDocumentTitle] = useState("");
  const [documentProxy, setDocumentProxy] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [scale, setScale] = useState(1);
  const [pageSize, setPageSize] = useState({ width: DEFAULT_PAGE_WIDTH, height: DEFAULT_PAGE_HEIGHT });
  const [annotations, setAnnotations] = useState<PdfAnnotationRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [autoCreateClaim, setAutoCreateClaim] = useState(false);

  const selectedAnnotation = useMemo(
    () => annotations.find((annotation) => annotation.sidecar_record_id === selectedId) ?? null,
    [annotations, selectedId],
  );

  useEffect(() => {
    void listAnnotations(SOURCE_ID)
      .then(setAnnotations)
      .catch(() => setAnnotations([]));
  }, []);

  useEffect(() => {
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
        renderTaskRef.current?.cancel();
        const renderTask = pdfPage.render({ canvas, canvasContext: context, viewport });
        renderTaskRef.current = renderTask;
        await renderTask.promise;
        if (!disposed) setReaderState("ready");
      })
      .catch((reason) => {
        if (disposed) return;
        setReaderState("failure");
        setError(reason instanceof Error ? reason.message : "Unable to render PDF page");
      });
    return () => {
      disposed = true;
      renderTaskRef.current?.cancel();
    };
  }, [documentProxy, page, scale]);

  async function openPdf(file: File) {
    if (file.type && file.type !== "application/pdf") {
      setReaderState("permission-denied");
      setError("Only local PDF files are accepted by this reader.");
      return;
    }
    setReaderState("loading");
    setError("");
    setDocumentTitle(file.name);
    try {
      const data = new Uint8Array(await file.arrayBuffer());
      const loaded = await pdfjsLib.getDocument({ data }).promise;
      setDocumentProxy(loaded);
      setPage(1);
      setPageCount(loaded.numPages);
    } catch (reason) {
      setReaderState("failure");
      setError(reason instanceof Error ? reason.message : "Unable to open PDF");
    }
  }

  async function addHighlight() {
    const selection = window.getSelection()?.toString() ?? "";
    const draft = annotationDraftFromSelection({
      page,
      text: selection,
      rect: { left: 92, top: 112, width: 260, height: 24 },
      pageWidth: pageSize.width,
      pageHeight: pageSize.height,
    });
    const fallback: PdfAnnotationRecord = {
      sidecar_record_id: `local-${Date.now()}`,
      source_id: SOURCE_ID,
      page: draft.page,
      text: draft.text,
      quad_points: draft.quad_points,
      bbox: { left: 0.15, top: 0.14, width: 0.42, height: 0.03 },
      type: draft.type,
      linked_claim_ids: [],
      linked_note_ids: [],
      color: draft.color,
      rev: 1,
      content_hash: "",
      link_state: "live",
      trust_origin: "user",
    };
    try {
      const created = await createAnnotation(SOURCE_ID, draft);
      setAnnotations((current) => [...current, created]);
      setSelectedId(created.sidecar_record_id);
    } catch {
      setAnnotations((current) => [...current, fallback]);
      setSelectedId(fallback.sidecar_record_id);
    }
  }

  async function routeClaimAction() {
    if (!selectedAnnotation) return;
    await createClaimFromAnnotation(selectedAnnotation.sidecar_record_id, autoCreateClaim).catch(() => undefined);
  }

  return (
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
        <button disabled={!documentProxy || page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))} aria-label="Previous page">
          <ChevronLeft size={14} />
        </button>
        <span className="pdf-page-count">{documentProxy ? `${page} / ${pageCount}` : "0 / 0"}</span>
        <button
          disabled={!documentProxy || page >= pageCount}
          onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
          aria-label="Next page"
        >
          <ChevronRight size={14} />
        </button>
        <button disabled={!documentProxy} onClick={() => setScale((current) => Math.max(0.7, Number((current - 0.1).toFixed(2))))} aria-label="Zoom out">
          <Minus size={14} />
        </button>
        <button disabled={!documentProxy} onClick={() => setScale((current) => Math.min(2, Number((current + 0.1).toFixed(2))))} aria-label="Zoom in">
          <Plus size={14} />
        </button>
        <button disabled={!documentProxy} onClick={() => setScale(1)} aria-label="Reset zoom">
          <RotateCcw size={14} />
        </button>
        <button disabled={!documentProxy} onClick={addHighlight}>
          <Highlighter size={14} /> Highlight
        </button>
      </header>

      <div className="pdf-reader-grid">
        <div className="pdf-stage" data-state={readerState}>
          {readerState === "empty" && (
            <div className="empty-panel">
              <p>No document open</p>
              <button onClick={() => fileInputRef.current?.click()}>
                <FileUp size={14} /> Open a PDF
              </button>
            </div>
          )}
          {readerState === "loading" && <div className="skeleton pdf-skeleton" aria-busy="true" />}
          {(readerState === "failure" || readerState === "permission-denied") && (
            <div className={`inline-state ${readerState === "failure" ? "failure" : "permission"}`} role="alert">
              <strong>{readerState}</strong>
              <span>{error}</span>
              <button onClick={() => fileInputRef.current?.click()}>Open another PDF</button>
            </div>
          )}
          <div className={`pdf-page-host ${documentProxy ? "ready" : ""}`} aria-label={documentTitle || "PDF page"}>
            <canvas ref={canvasRef} />
            {documentProxy && (
              <AnnotationLayer
                annotations={annotations}
                page={page}
                pageWidth={pageSize.width}
                pageHeight={pageSize.height}
                scale={scale}
                selectedId={selectedId}
                onSelect={(annotation) => setSelectedId(annotation.sidecar_record_id)}
              />
            )}
          </div>
        </div>
        <AnnotationInspector
          annotation={selectedAnnotation}
          autoCreateClaim={autoCreateClaim}
          onAutoCreateClaim={setAutoCreateClaim}
          onClaimAction={routeClaimAction}
        />
      </div>
    </section>
  );
}
