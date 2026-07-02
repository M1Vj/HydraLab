import {
  createAnnotation,
  createClaimFromAnnotation,
  listAnnotations,
  type AnnotationDraft,
  type PdfAnnotationRecord,
} from "../../lib/annotations/store";

const MAX_RENDER_SCALE = 2;
const MIN_RENDER_SCALE = 0.7;

export function clampPage(page: number, pageCount: number): number {
  if (pageCount <= 0) return 1;
  return Math.min(Math.max(1, Math.trunc(page)), pageCount);
}

export function clampScale(scale: number): number {
  return Math.min(MAX_RENDER_SCALE, Math.max(MIN_RENDER_SCALE, Number(scale.toFixed(2))));
}

type Destroyable = { destroy: () => void | Promise<void> };
type Cancellable = { cancel: () => void };

/**
 * Owns the pdf.js document + render-task lifecycle so the panel never leaks a
 * PDFDocumentProxy or an in-flight render task. Kept framework-free so the
 * cleanup contract can be unit tested with mock pdf.js objects.
 */
export class PdfLifecycle {
  private document: Destroyable | null = null;
  private renderTask: Cancellable | null = null;

  get current(): Destroyable | null {
    return this.document;
  }

  setDocument(next: Destroyable | null): void {
    if (this.document && this.document !== next) {
      void this.document.destroy();
    }
    this.document = next;
  }

  trackRender(task: Cancellable | null): void {
    if (this.renderTask && this.renderTask !== task) {
      this.renderTask.cancel();
    }
    this.renderTask = task;
  }

  cancelRender(): void {
    this.renderTask?.cancel();
    this.renderTask = null;
  }

  destroy(): void {
    this.renderTask?.cancel();
    this.renderTask = null;
    if (this.document) {
      void this.document.destroy();
      this.document = null;
    }
  }
}

export type AnnotationDeps = {
  listAnnotations: (sourceId: string) => Promise<PdfAnnotationRecord[]>;
  createAnnotation: (sourceId: string, draft: AnnotationDraft) => Promise<PdfAnnotationRecord>;
  createClaimFromAnnotation: (
    sidecarRecordId: string,
    autoCreate: boolean,
  ) => Promise<{ created_claim: { id: string; status: string; text: string } | null; review_item: unknown }>;
};

export const defaultAnnotationDeps: AnnotationDeps = {
  listAnnotations,
  createAnnotation,
  createClaimFromAnnotation,
};

export function loadSourceAnnotations(sourceId: string, deps: AnnotationDeps = defaultAnnotationDeps): Promise<PdfAnnotationRecord[]> {
  return deps.listAnnotations(sourceId);
}

export function addHighlight(sourceId: string, draft: AnnotationDraft, deps: AnnotationDeps = defaultAnnotationDeps): Promise<PdfAnnotationRecord> {
  return deps.createAnnotation(sourceId, draft);
}

export function suggestClaim(
  sidecarRecordId: string,
  autoCreate: boolean,
  deps: AnnotationDeps = defaultAnnotationDeps,
): Promise<{ created_claim: { id: string; status: string; text: string } | null; review_item: unknown }> {
  return deps.createClaimFromAnnotation(sidecarRecordId, autoCreate);
}
