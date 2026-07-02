export type EditorMode = "live" | "source" | "split";

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

export function renderMarkdownPreview(markdown: string, context: MarkdownContext): string {
  const inlineDecorations = decorateMarkdown(markdown, context).filter((item) => item.kind !== "callout");
  const highlights = [...(context.highlights ?? [])].sort((left, right) => left.from - right.from || left.to - right.to);
  const ranges = [...inlineDecorations, ...highlights.map((highlight) => ({ ...highlight, kind: "highlight" as const }))]
    .filter((range) => range.from >= 0 && range.to > range.from && range.to <= markdown.length)
    .sort((left, right) => left.from - right.from || left.to - right.to);
  let cursor = 0;
  let html = "";
  for (const range of ranges) {
    if (range.from < cursor) continue;
    html += escapeHtml(markdown.slice(cursor, range.from));
    const raw = markdown.slice(range.from, range.to);
    if (range.kind === "wikilink") {
      const state = range.resolved ? "resolved" : "dangling";
      html += `<span class="md-wikilink" data-state="${state}" data-note-id="${escapeHtml(range.targetId ?? "")}">${escapeHtml(raw)}</span>`;
    } else if (range.kind === "citation") {
      const state = range.resolved ? "resolved" : "dangling";
      html += `<span class="md-citation" data-state="${state}" data-source-id="${escapeHtml(range.sourceId ?? "")}">${escapeHtml(raw)}</span>`;
    } else {
      html += `<mark class="md-${range.type}-highlight" data-highlight="${range.type}" data-id="${escapeHtml(range.id)}">${escapeHtml(raw)}</mark>`;
    }
    cursor = range.to;
  }
  html += escapeHtml(markdown.slice(cursor));

  const lines = html.split("\n");
  const sourceLines = markdown.split("\n");
  return lines
    .map((line, index) => {
      const callout = /^&gt;\s*\[!([A-Za-z0-9_-]+)\](?:\s+(.+))?/.exec(line);
      if (!callout) {
        return line || "<br>";
      }
      const title = callout[2]?.trim() || callout[1];
      return `<div class="md-callout md-callout-${callout[1].toLowerCase()}" data-callout="${callout[1].toLowerCase()}"><strong>${title}</strong><span class="sr-only">${escapeHtml(sourceLines[index] ?? "")}</span></div>`;
    })
    .join("\n");
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
