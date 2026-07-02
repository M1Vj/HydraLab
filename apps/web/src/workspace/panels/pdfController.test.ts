import { describe, expect, mock, test } from "bun:test";

import { addHighlight, clampPage, clampScale, loadSourceAnnotations, PdfLifecycle, suggestClaim, type AnnotationDeps } from "./pdfController";
import type { AnnotationDraft, PdfAnnotationRecord } from "../../lib/annotations/store";

function fakeAnnotation(id: string, page = 1): PdfAnnotationRecord {
  return {
    sidecar_record_id: id,
    source_id: "src_attention",
    page,
    text: "scaled attention",
    quad_points: [0.1, 0.1, 0.5, 0.1, 0.5, 0.2, 0.1, 0.2],
    bbox: { left: 0.1, top: 0.1, width: 0.4, height: 0.1 },
    type: "highlight",
    linked_claim_ids: [],
    linked_note_ids: [],
    color: "yellow",
    rev: 1,
    content_hash: "",
    link_state: "live",
    trust_origin: "user",
  };
}

describe("pdf page navigation", () => {
  test("clampPage stays within [1, pageCount] for large documents", () => {
    expect(clampPage(0, 250)).toBe(1);
    expect(clampPage(999, 250)).toBe(250);
    expect(clampPage(42, 250)).toBe(42);
    expect(clampPage(3, 0)).toBe(1);
  });

  test("clampScale bounds zoom", () => {
    expect(clampScale(0.1)).toBe(0.7);
    expect(clampScale(9)).toBe(2);
    expect(clampScale(1.25)).toBe(1.25);
  });
});

describe("pdf lifecycle cleanup", () => {
  test("destroy() destroys the document and cancels the render task on unmount", () => {
    const destroy = mock(() => undefined);
    const cancel = mock(() => undefined);
    const lifecycle = new PdfLifecycle();

    lifecycle.setDocument({ destroy });
    lifecycle.trackRender({ cancel });
    lifecycle.destroy();

    expect(destroy).toHaveBeenCalledTimes(1);
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(lifecycle.current).toBeNull();
  });

  test("replacing the document destroys the previous proxy", () => {
    const destroyFirst = mock(() => undefined);
    const destroySecond = mock(() => undefined);
    const lifecycle = new PdfLifecycle();

    lifecycle.setDocument({ destroy: destroyFirst });
    lifecycle.setDocument({ destroy: destroySecond });

    expect(destroyFirst).toHaveBeenCalledTimes(1);
    expect(destroySecond).not.toHaveBeenCalled();
  });

  test("tracking a new render task cancels the previous one", () => {
    const cancelFirst = mock(() => undefined);
    const cancelSecond = mock(() => undefined);
    const lifecycle = new PdfLifecycle();

    lifecycle.trackRender({ cancel: cancelFirst });
    lifecycle.trackRender({ cancel: cancelSecond });

    expect(cancelFirst).toHaveBeenCalledTimes(1);
    expect(cancelSecond).not.toHaveBeenCalled();
  });
});

describe("annotation open flow", () => {
  function deps(overrides: Partial<AnnotationDeps> = {}): AnnotationDeps {
    return {
      listAnnotations: mock(async (_sourceId: string) => [fakeAnnotation("ann-1")]),
      createAnnotation: mock(async (_sourceId: string, draft: AnnotationDraft) => ({ ...fakeAnnotation("ann-2"), ...draft, sidecar_record_id: "ann-2" })),
      createClaimFromAnnotation: mock(async (_recordId: string, _autoCreate: boolean) => ({ created_claim: null, review_item: { id: "rev-1" } })),
      ...overrides,
    };
  }

  test("sourceId loads annotations through the store", async () => {
    const injected = deps();
    const annotations = await loadSourceAnnotations("src_attention", injected);

    expect(injected.listAnnotations).toHaveBeenCalledWith("src_attention");
    expect(annotations).toHaveLength(1);
    expect(annotations[0]?.sidecar_record_id).toBe("ann-1");
  });

  test("adding a highlight posts the draft to the source", async () => {
    const injected = deps();
    const draft: AnnotationDraft = { page: 1, text: "scaled attention", quad_points: [0, 0, 1, 0, 1, 1, 0, 1], type: "highlight", color: "yellow" };
    const created = await addHighlight("src_attention", draft, injected);

    expect(injected.createAnnotation).toHaveBeenCalledWith("src_attention", draft);
    expect(created.sidecar_record_id).toBe("ann-2");
  });

  test("suggest claim posts the record id and auto-create flag", async () => {
    const injected = deps();
    const result = await suggestClaim("ann-1", false, injected);

    expect(injected.createClaimFromAnnotation).toHaveBeenCalledWith("ann-1", false);
    expect(result.review_item).toEqual({ id: "rev-1" });
  });
});
