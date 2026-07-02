import DOMPurify from "dompurify";

export type EditorMode = "live" | "source" | "split";

// Allowlist for the preview HTML. The renderer already escapes all user text and
// only emits this fixed tag/attribute set, so DOMPurify is defense-in-depth for
// the dangerouslySetInnerHTML sink (e.g. assistant- or collaboration-authored
// Markdown). In a non-DOM environment (tests/SSR) sanitize is skipped — the
// escape-first output is safe on its own there.
const PREVIEW_ALLOWED_TAGS = [
  "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "ul", "ol", "li",
  "blockquote", "pre", "code", "strong", "em", "a", "span", "mark", "div",
];
const PREVIEW_ALLOWED_ATTR = [
  "class", "href", "rel", "target", "data-state", "data-note-id",
  "data-source-id", "data-highlight", "data-id", "data-callout",
];

function sanitizePreview(html: string): string {
  if (typeof window === "undefined" || typeof DOMPurify.sanitize !== "function") return html;
  return DOMPurify.sanitize(html, { ALLOWED_TAGS: PREVIEW_ALLOWED_TAGS, ALLOWED_ATTR: PREVIEW_ALLOWED_ATTR });
}

export type CitationOption = {
  key: string;
  sourceId: string;
  title: string;
};

export type NoteOption = {
  id: string;
  title: string;
};

export type TextHighlight = {
  id: string;
  type: "claim" | "evidence";
  from: number;
  to: number;
};

export type InlineSuggestion = {
  id: string;
  from: number;
  to: number;
  replacement: string;
};

export type MarkdownContext = {
  notes: NoteOption[];
  citations: CitationOption[];
  highlights?: TextHighlight[];
};

export type MarkdownDecoration =
  | {
      kind: "callout";
      from: number;
      to: number;
      calloutType: string;
      title: string;
    }
  | {
      kind: "wikilink";
      from: number;
      to: number;
      target: string;
      targetId?: string;
      resolved: boolean;
    }
  | {
      kind: "citation";
      from: number;
      to: number;
      key: string;
      sourceId?: string;
      resolved: boolean;
    };

export function nextEditorMode(mode: EditorMode): EditorMode {
  if (mode === "live") return "source";
  if (mode === "source") return "split";
  return "live";
}

export function decorateMarkdown(markdown: string, context: MarkdownContext): MarkdownDecoration[] {
  const decorations: MarkdownDecoration[] = [];
  let offset = 0;
  for (const line of markdown.split(/(\n)/)) {
    if (line === "\n") {
      offset += line.length;
      continue;
    }
    const callout = /^>\s*\[!([A-Za-z0-9_-]+)\](?:\s+(.+))?/.exec(line);
    if (callout) {
      decorations.push({
        kind: "callout",
        from: offset,
        to: offset + callout[0].length,
        calloutType: callout[1].toLowerCase(),
        title: callout[2]?.trim() ?? "",
      });
    }
    for (const match of line.matchAll(/\[\[([^\]|]+)(?:\|[^\]]*)?\]\]/g)) {
      const target = match[1].trim();
      const note = context.notes.find((candidate) => candidate.id === target || candidate.title.toLowerCase() === target.toLowerCase());
      decorations.push({
        kind: "wikilink",
        from: offset + match.index,
        to: offset + match.index + match[0].length,
        target,
        targetId: note?.id,
        resolved: Boolean(note),
      });
    }
    for (const match of line.matchAll(/\[@([A-Za-z0-9_:.#/-]+)\]/g)) {
      const key = match[1].trim();
      const citation = context.citations.find((candidate) => candidate.key === key);
      decorations.push({
        kind: "citation",
        from: offset + match.index,
        to: offset + match.index + match[0].length,
        key,
        sourceId: citation?.sourceId,
        resolved: Boolean(citation),
      });
    }
    offset += line.length;
  }
  return decorations.sort((left, right) => left.from - right.from || left.to - right.to);
}

// Render Markdown to safe HTML for the live preview. Block structure (headings,
// lists, blockquotes, fenced code, rules, paragraphs) plus inline formatting
// (bold/italic/code/links) is rendered, while HydraLab's own decorations
// (wikilinks [[..]], citations [@..], claim/evidence highlights, callouts) are
// preserved. Everything is HTML-escaped before formatting so the preview can be
// injected with dangerouslySetInnerHTML without an XSS vector.
export function renderMarkdownPreview(markdown: string, context: MarkdownContext): string {
  const lines = markdown.split("\n");
  const lineOffsets: number[] = [];
  {
    let running = 0;
    for (const line of lines) {
      lineOffsets.push(running);
      running += line.length + 1; // +1 for the split "\n"
    }
  }

  const blocks: string[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];

    // Fenced code block: verbatim, no formatting or decoration.
    const fence = /^```(.*)$/.exec(line);
    if (fence) {
      const lang = fence[1].trim();
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !/^```/.test(lines[index])) {
        body.push(lines[index]);
        index += 1;
      }
      index += 1; // consume closing fence (if present)
      const langClass = lang ? ` class="language-${escapeHtml(lang)}"` : "";
      blocks.push(`<pre class="md-code"><code${langClass}>${escapeHtml(body.join("\n"))}</code></pre>`);
      continue;
    }

    if (line.trim() === "") {
      index += 1;
      continue;
    }

    // Callout (kept from the prior behavior).
    const callout = /^>\s*\[!([A-Za-z0-9_-]+)\](?:\s+(.+))?/.exec(line);
    if (callout) {
      const type = callout[1].toLowerCase();
      const title = callout[2]?.trim() || callout[1];
      blocks.push(`<div class="md-callout md-callout-${type}" data-callout="${type}"><strong>${escapeHtml(title)}</strong></div>`);
      index += 1;
      continue;
    }

    // Heading.
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const textOffset = lineOffsets[index] + (line.length - heading[2].length);
      blocks.push(`<h${level}>${renderInline(heading[2], textOffset, context)}</h${level}>`);
      index += 1;
      continue;
    }

    // Horizontal rule.
    if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push("<hr />");
      index += 1;
      continue;
    }

    // Blockquote (non-callout), possibly multi-line.
    if (/^>\s?/.test(line) && !/^>\s*\[!/.test(line)) {
      const parts: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index]) && !/^>\s*\[!/.test(lines[index])) {
        const match = /^>\s?(.*)$/.exec(lines[index]);
        const content = match ? match[1] : "";
        const contentOffset = lineOffsets[index] + (lines[index].length - content.length);
        parts.push(renderInline(content, contentOffset, context));
        index += 1;
      }
      blocks.push(`<blockquote>${parts.join("<br />")}</blockquote>`);
      continue;
    }

    // Lists (unordered or ordered), consecutive items of the same kind.
    const ordered = /^\s*\d+\.\s+/.test(line);
    const unordered = /^\s*[-*+]\s+/.test(line);
    if (ordered || unordered) {
      const items: string[] = [];
      const itemPattern = ordered ? /^\s*\d+\.\s+(.*)$/ : /^\s*[-*+]\s+(.*)$/;
      while (index < lines.length && itemPattern.test(lines[index])) {
        const match = itemPattern.exec(lines[index]);
        const content = match ? match[1] : "";
        const contentOffset = lineOffsets[index] + (lines[index].length - content.length);
        items.push(`<li>${renderInline(content, contentOffset, context)}</li>`);
        index += 1;
      }
      const tag = ordered ? "ol" : "ul";
      blocks.push(`<${tag}>${items.join("")}</${tag}>`);
      continue;
    }

    // Paragraph: accumulate consecutive plain lines.
    const paragraph: string[] = [];
    while (index < lines.length && isParagraphLine(lines[index])) {
      paragraph.push(renderInline(lines[index], lineOffsets[index], context));
      index += 1;
    }
    blocks.push(`<p>${paragraph.join("<br />")}</p>`);
  }

  return sanitizePreview(blocks.join("\n"));
}

function isParagraphLine(line: string): boolean {
  if (line.trim() === "") return false;
  return !(
    /^```/.test(line) ||
    /^#{1,6}\s+/.test(line) ||
    /^>\s?/.test(line) ||
    /^\s*[-*+]\s+/.test(line) ||
    /^\s*\d+\.\s+/.test(line) ||
    /^(-{3,}|\*{3,}|_{3,})\s*$/.test(line)
  );
}

// Render one line/segment of inline content: splice in the offset-based
// decorations (wikilinks/citations/highlights) and apply inline Markdown
// formatting to the plain text between them.
function renderInline(text: string, docOffset: number, context: MarkdownContext): string {
  const localDecorations = decorateMarkdown(text, context).filter((item) => item.kind !== "callout");
  const localHighlights = (context.highlights ?? [])
    .filter((highlight) => highlight.from >= docOffset && highlight.to <= docOffset + text.length && highlight.to > highlight.from)
    .map((highlight) => ({ ...highlight, kind: "highlight" as const, from: highlight.from - docOffset, to: highlight.to - docOffset }));
  const ranges = [...localDecorations, ...localHighlights]
    .filter((range) => range.from >= 0 && range.to > range.from && range.to <= text.length)
    .sort((left, right) => left.from - right.from || left.to - right.to);

  let cursor = 0;
  let html = "";
  for (const range of ranges) {
    if (range.from < cursor) continue;
    html += formatInline(escapeHtml(text.slice(cursor, range.from)));
    const raw = escapeHtml(text.slice(range.from, range.to));
    if (range.kind === "wikilink") {
      html += `<span class="md-wikilink" data-state="${range.resolved ? "resolved" : "dangling"}" data-note-id="${escapeHtml(range.targetId ?? "")}">${raw}</span>`;
    } else if (range.kind === "citation") {
      html += `<span class="md-citation" data-state="${range.resolved ? "resolved" : "dangling"}" data-source-id="${escapeHtml(range.sourceId ?? "")}">${raw}</span>`;
    } else {
      html += `<mark class="md-${range.type}-highlight" data-highlight="${range.type}" data-id="${escapeHtml(range.id)}">${raw}</mark>`;
    }
    cursor = range.to;
  }
  html += formatInline(escapeHtml(text.slice(cursor)));
  return html;
}

// Inline Markdown on ALREADY-ESCAPED plain text (no HTML tags present in the
// input, so the regexes cannot span or corrupt existing markup).
function formatInline(escaped: string): string {
  return escaped
    .replace(/`([^`]+)`/g, (_match, code) => `<code>${code}</code>`)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>")
    .replace(/(^|[^_\w])_([^_\n]+)_(?![_\w])/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_match, label, url) => {
      const safe = /^(https?:|mailto:|#|\/)/i.test(url) ? url : "#";
      return `<a href="${safe}" rel="noreferrer noopener" target="_blank">${label}</a>`;
    });
}

export function applyInlineSuggestion(content: string, suggestion: InlineSuggestion, action: "accept" | "reject" | "ignore"): string {
  if (action !== "accept") return content;
  return `${content.slice(0, suggestion.from)}${suggestion.replacement}${content.slice(suggestion.to)}`;
}

export function buildSelectionContext(input: {
  fileRef: string;
  content: string;
  from: number;
  to: number;
  mode: EditorMode;
}) {
  const from = Math.max(0, Math.min(input.from, input.content.length));
  const to = Math.max(from, Math.min(input.to, input.content.length));
  return {
    fileRef: input.fileRef,
    mode: input.mode,
    cursor: to,
    selectedText: input.content.slice(from, to),
    selection: { from, to },
  };
}

export function insertCitationToken(content: string, cursor: number, key: string): { content: string; cursor: number } {
  const safeCursor = Math.max(0, Math.min(cursor, content.length));
  const token = `[@${key}]`;
  return {
    content: `${content.slice(0, safeCursor)}${token}${content.slice(safeCursor)}`,
    cursor: safeCursor + token.length,
  };
}

export function recoverableAutosaveState(input: {
  dirty: boolean;
  focused: boolean;
  elapsedMs: number;
  idleMs?: number;
}) {
  const idleMs = input.idleMs ?? 1000;
  return {
    shouldSave: input.dirty && (!input.focused || input.elapsedMs >= idleMs),
    shouldJournal: input.dirty,
    sideEffects: [] as string[],
  };
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
