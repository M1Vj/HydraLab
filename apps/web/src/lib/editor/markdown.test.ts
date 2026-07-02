import { describe, expect, test } from "bun:test";
import {
  applyInlineSuggestion,
  buildSelectionContext,
  decorateMarkdown,
  insertCitationToken,
  nextEditorMode,
  recoverableAutosaveState,
  renderMarkdownPreview,
} from "./markdown";

describe("Markdown editor behavior", () => {
  test("@HL-WRITE-02 cycles live, source and split modes", () => {
    expect(nextEditorMode("live")).toBe("source");
    expect(nextEditorMode("source")).toBe("split");
    expect(nextEditorMode("split")).toBe("live");
  });

  test("@HL-WRITE-04 @HL-WRITE-05 @HL-WRITE-06 decorates wikilinks citations and callouts", () => {
    const decorations = decorateMarkdown(
      "> [!warning] Reproducibility\nSee [[Attention Is All You Need]] and [@vaswani2017].",
      {
        notes: [{ id: "n-7af3", title: "Attention Is All You Need" }],
        citations: [{ key: "vaswani2017", sourceId: "src-attention", title: "Attention Is All You Need" }],
      },
    );

    expect(decorations.map((item) => item.kind)).toEqual(["callout", "wikilink", "citation"]);
    expect(decorations[1]).toMatchObject({ resolved: true, targetId: "n-7af3" });
    expect(decorations[2]).toMatchObject({ resolved: true, sourceId: "src-attention" });
  });

  test("@HL-WRITE-04 unresolved links render as dangling without deleting text", () => {
    const html = renderMarkdownPreview("See [[Missing Note]] and [@missing].", { notes: [], citations: [] });

    expect(html).toContain("Missing Note");
    expect(html).toContain("data-state=\"dangling\"");
    expect(html).toContain("[@missing]");
  });

  test("@HL-WRITE-08 highlights claim and evidence locators", () => {
    const html = renderMarkdownPreview("Claim sentence. Evidence phrase.", {
      notes: [],
      citations: [],
      highlights: [
        { id: "claim-1", type: "claim", from: 0, to: 14 },
        { id: "evidence-1", type: "evidence", from: 16, to: 31 },
      ],
    });

    expect(html).toContain("data-highlight=\"claim\"");
    expect(html).toContain("data-highlight=\"evidence\"");
  });

  test("@HL-WRITE-09 applies suggestions only on explicit accept", () => {
    const suggestion = { id: "s1", from: 0, to: 5, replacement: "Hello" };

    expect(applyInlineSuggestion("World text", suggestion, "ignore")).toBe("World text");
    expect(applyInlineSuggestion("World text", suggestion, "accept")).toBe("Hello text");
    expect(applyInlineSuggestion("World text", suggestion, "reject")).toBe("World text");
  });

  test("@HL-WRITE-10 selection context survives mode changes", () => {
    const selected = "scaled dot-product attention";
    const context = buildSelectionContext({
      fileRef: "knowledge/Methods.md",
      content: selected,
      from: 0,
      to: selected.length,
      mode: "live",
    });

    const afterToggle = buildSelectionContext({
      fileRef: "knowledge/Methods.md",
      content: selected,
      from: context.selection.from,
      to: context.selection.to,
      mode: "split",
    });

    expect(afterToggle.selectedText).toBe(selected);
    expect(afterToggle.fileRef).toBe(context.fileRef);
  });

  test("@HL-WRITE-11 inserts stable citation key tokens at the cursor", () => {
    expect(insertCitationToken("See .", 4, "vaswani2017")).toEqual({
      content: "See [@vaswani2017].",
      cursor: 18,
    });
  });

  test("@HL-WRITE-12 autosave state is local only and recoverable", () => {
    expect(recoverableAutosaveState({ dirty: true, focused: false, elapsedMs: 1200 })).toMatchObject({
      shouldSave: true,
      shouldJournal: true,
      sideEffects: [],
    });
    expect(recoverableAutosaveState({ dirty: true, focused: true, elapsedMs: 200 })).toMatchObject({
      shouldSave: false,
      shouldJournal: true,
      sideEffects: [],
    });
  });
});
