export type AnnotationType = "highlight" | "underline" | "note";

export type PdfAnnotationRecord = {
  sidecar_record_id: string;
  source_id: string;
  page: number;
  text: string;
  quad_points: number[];
  bbox: { left: number; top: number; width: number; height: number };
  type: AnnotationType;
  linked_claim_ids: string[];
  linked_note_ids: string[];
  color: string;
  rev: number;
  content_hash: string;
  link_state: "live" | "target_trashed" | string;
  trust_origin: "user" | string;
};

export type AnnotationDraft = {
  page: number;
  text: string;
  quad_points: number[];
  type: AnnotationType;
  color: string;
  linked_claim_ids?: string[];
  linked_note_ids?: string[];
};

export type ViewportRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

function apiBaseUrl(): string | null {
  const configured = import.meta.env.VITE_HYDRA_API_BASE_URL as string | undefined;
  if (configured) return configured.replace(/\/$/, "");
  if (!import.meta.env.DEV) return "";
  return null;
}

function annotationApiPath(path: string): string {
  const base = apiBaseUrl();
  if (base === null) {
    throw new Error("Hydra annotation API is not configured for this dev server");
  }
  return `${base}${path}`;
}

export function normalizedQuadFromRect(rect: ViewportRect, pageWidth: number, pageHeight: number): number[] {
  if (pageWidth <= 0 || pageHeight <= 0) {
    throw new Error("page dimensions must be positive");
  }
  const left = rect.left / pageWidth;
  const top = rect.top / pageHeight;
  const right = (rect.left + rect.width) / pageWidth;
  const bottom = (rect.top + rect.height) / pageHeight;
  return [left, top, right, top, right, bottom, left, bottom].map((value) => Number(Math.max(0, Math.min(1, value)).toFixed(6)));
}

export function viewportRectFromQuad(quadPoints: number[], pageWidth: number, pageHeight: number, scale: number): ViewportRect {
  if (quadPoints.length !== 8) {
    throw new Error("quad points must contain 8 numbers");
  }
  const xs = [quadPoints[0], quadPoints[2], quadPoints[4], quadPoints[6]];
  const ys = [quadPoints[1], quadPoints[3], quadPoints[5], quadPoints[7]];
  const left = Math.min(...xs) * pageWidth * scale;
  const top = Math.min(...ys) * pageHeight * scale;
  const width = (Math.max(...xs) - Math.min(...xs)) * pageWidth * scale;
  const height = (Math.max(...ys) - Math.min(...ys)) * pageHeight * scale;
  return {
    left: Math.round(left),
    top: Math.round(top),
    width: Math.round(width),
    height: Math.round(height),
  };
}

export function annotationDraftFromSelection(input: {
  page: number;
  text: string;
  rect: ViewportRect;
  pageWidth: number;
  pageHeight: number;
  color?: string;
}): AnnotationDraft {
  return {
    page: input.page,
    text: input.text.trim() || "Selected passage",
    type: "highlight",
    color: input.color ?? "yellow",
    quad_points: normalizedQuadFromRect(input.rect, input.pageWidth, input.pageHeight),
  };
}

export function shouldAutoCreateClaim(autoCreateEnabled: boolean): boolean {
  return autoCreateEnabled;
}

export async function listAnnotations(sourceId: string): Promise<PdfAnnotationRecord[]> {
  const base = apiBaseUrl();
  if (base === null) return [];
  const response = await fetch(`${base}/api/annotations/${encodeURIComponent(sourceId)}`);
  if (!response.ok) {
    throw new Error(`Failed to load annotations: ${response.status}`);
  }
  const payload = (await response.json()) as { annotations: PdfAnnotationRecord[] };
  return payload.annotations;
}

export async function createAnnotation(sourceId: string, draft: AnnotationDraft): Promise<PdfAnnotationRecord> {
  const response = await fetch(annotationApiPath(`/api/annotations/${encodeURIComponent(sourceId)}`), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(draft),
  });
  if (!response.ok) {
    throw new Error(`Failed to create annotation: ${response.status}`);
  }
  const payload = (await response.json()) as { annotation: PdfAnnotationRecord };
  return payload.annotation;
}

export async function createClaimFromAnnotation(sidecarRecordId: string, autoCreate: boolean) {
  const response = await fetch(annotationApiPath(`/api/annotations/${encodeURIComponent(sidecarRecordId)}/claim`), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ auto_create: shouldAutoCreateClaim(autoCreate) }),
  });
  if (!response.ok) {
    throw new Error(`Failed to route annotation claim action: ${response.status}`);
  }
  return response.json() as Promise<{ created_claim: { id: string; status: string; text: string } | null; review_item: unknown }>;
}
