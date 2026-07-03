import { describe, expect, test } from "bun:test";

import {
  annotationDraftFromSelection,
  normalizedQuadFromRect,
  pageRectFromSelection,
  shouldAutoCreateClaim,
  viewportRectFromQuad,
} from "./store";

describe("PDF annotation helpers", () => {
  test("@HL-PDF-03 stores page anchors as normalized quad points", () => {
    const quad = normalizedQuadFromRect({ left: 120, top: 180, width: 240, height: 36 }, 600, 800);

    expect(quad).toEqual([0.2, 0.225, 0.6, 0.225, 0.6, 0.27, 0.2, 0.27]);
    expect(viewportRectFromQuad(quad, 600, 800, 1.75)).toEqual({ left: 210, top: 315, width: 420, height: 63 });
  });

  test("@HL-PDF-09 defaults claim creation to review suggestion", () => {
    expect(shouldAutoCreateClaim(false)).toBe(false);
    expect(shouldAutoCreateClaim(true)).toBe(true);
  });

  test("@HL-PDF-04 drafts highlights from selection without viewport-pixel storage", () => {
    const draft = annotationDraftFromSelection({
      page: 2,
      text: " scaled attention ",
      rect: { left: 10, top: 20, width: 100, height: 12 },
      pageWidth: 500,
      pageHeight: 700,
    });

    expect(draft).toMatchObject({ page: 2, text: "scaled attention", type: "highlight", color: "yellow" });
    expect(draft.quad_points.every((point) => point >= 0 && point <= 1)).toBe(true);
  });

  test("@HL-PDF-04 maps a real text selection to unscaled page coordinates", () => {
    // Canvas rendered at 2x zoom, positioned at (100, 50) in the viewport.
    const canvas = { left: 100, top: 50, width: 1224, height: 1584 };
    const selection = { left: 300, top: 250, width: 200, height: 40 };

    const rect = pageRectFromSelection(selection, canvas, 2);
    // (300-100)/2, (250-50)/2, 200/2, 40/2
    expect(rect).toEqual({ left: 100, top: 100, width: 100, height: 20 });
  });

  test("@HL-PDF-04 rejects an empty or off-page selection", () => {
    const canvas = { left: 100, top: 50, width: 1224, height: 1584 };
    expect(pageRectFromSelection({ left: 300, top: 250, width: 0, height: 40 }, canvas, 2)).toBeNull();
    // A selection entirely to the left of the page does not overlap it.
    expect(pageRectFromSelection({ left: 0, top: 250, width: 50, height: 40 }, canvas, 2)).toBeNull();
  });
});
