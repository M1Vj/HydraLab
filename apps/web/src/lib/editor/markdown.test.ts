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

  test("renders block markdown to real HTML (headings, lists, code, rule)", () => {
    const html = renderMarkdownPreview(
      "# Title\n\nA paragraph.\n\n- one\n- two\n\n```\ncode line\n```\n\n---\n\n> quoted",
      { notes: [], citations: [] },
    );
    expect(html).toContain("<h1>Title</h1>");
    expect(html).toContain("<p>A paragraph.</p>");
    expect(html).toContain("<ul><li>one</li><li>two</li></ul>");
    expect(html).toContain("<pre class=\"md-code\"><code>code line</code></pre>");
    expect(html).toContain("<hr />");
    expect(html).toContain("<blockquote>quoted</blockquote>");
  });

  test("renders inline markdown (bold, italic, code, links)", () => {
    const html = renderMarkdownPreview("This is **bold**, *italic*, `mono` and a [link](https://x.test).", {
      notes: [],
      citations: [],
    });
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<em>italic</em>");
    expect(html).toContain("<code>mono</code>");
    expect(html).toContain("<a href=\"https://x.test\"");
  });

  test("orders lists and preserves wikilinks/citations inside rendered blocks", () => {
    const html = renderMarkdownPreview("1. see [[Intro]]\n2. cite [@smith]", {
      notes: [{ id: "n1", title: "Intro" }],
      citations: [{ key: "smith", sourceId: "s1", title: "Smith 2020" }],
    });
    expect(html).toContain("<ol>");
    expect(html).toContain("class=\"md-wikilink\" data-state=\"resolved\"");
    expect(html).toContain("class=\"md-citation\" data-state=\"resolved\"");
  });

  test("escapes raw HTML so the preview cannot inject markup (XSS)", () => {
    const html = renderMarkdownPreview("<img src=x onerror=alert(1)> and <script>alert(2)</script>", {
      notes: [],
      citations: [],
    });
    expect(html).not.toContain("<img");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });

  test("neutralizes dangerous link schemes", () => {
    const html = renderMarkdownPreview("[click](javascript:alert(1))", { notes: [], citations: [] });
    expect(html).not.toContain("javascript:");
    expect(html).toContain("href=\"#\"");
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
