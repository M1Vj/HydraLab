import React, { useEffect, useMemo, useRef, useState } from "react";
import { Check, Code2, Columns2, Eye, Quote, Save, Users, WifiOff, X } from "lucide-react";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { markdown } from "@codemirror/lang-markdown";
import { defaultHighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorState, type Range } from "@codemirror/state";
import { Decoration, DecorationSet, EditorView, keymap, ViewPlugin, ViewUpdate, WidgetType } from "@codemirror/view";
import * as Y from "yjs";
import { yCollab } from "y-codemirror.next";
import { commandRegistry } from "../../core/commands";
import {
  applyInlineSuggestion,
  buildSelectionContext,
  decorateMarkdown,
  insertCitationToken,
  nextEditorMode,
  recoverableAutosaveState,
  renderMarkdownPreview,
  type CitationOption,
  type EditorMode,
  type InlineSuggestion,
  type NoteOption,
  type TextHighlight,
} from "../../lib/editor/markdown";

type SaveState = "saved" | "dirty" | "saving" | "failed";
type SyncState = "offline" | "connecting" | "synced" | "syncing" | "conflict" | "revoked";
type RemoteUser = { id: string; displayName: string; color?: string };
type CollaborationConfig = {
  enabled: boolean;
  projectId: string;
  documentId: string;
  syncState: SyncState;
  remoteUsers: RemoteUser[];
};

export function HydraMarkdownEditor({
  fileRef,
  value,
  notes,
  citations,
  highlights = [],
  suggestions = [],
  trustOrigin = "user",
  collaboration,
  onChange,
  onSave,
}: {
  fileRef: string;
  value: string;
  notes: NoteOption[];
  citations: CitationOption[];
  highlights?: TextHighlight[];
  suggestions?: InlineSuggestion[];
  trustOrigin?: "user" | "assistant" | "untrusted";
  collaboration?: CollaborationConfig;
  onChange: (value: string) => void;
  onSave: (value: string) => Promise<void> | void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const collaborationRef = useRef<{ doc: Y.Doc; awareness: LocalAwareness; socket: WebSocket | null } | null>(null);
  const valueRef = useRef(value);
  const lastEditAtRef = useRef(Date.now());
  const [mode, setMode] = useState<EditorMode>("live");
  const [draft, setDraft] = useState(value);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [runtimeSyncState, setRuntimeSyncState] = useState<SyncState>(collaboration?.syncState ?? "offline");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState("");
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null);

  const context = useMemo(() => ({ notes, citations, highlights }), [notes, citations, highlights]);
  const preview = useMemo(() => renderMarkdownPreview(draft, context), [draft, context]);
  const filteredCitations = citations.filter((citation) => {
    const needle = pickerQuery.toLowerCase();
    return !needle || citation.title.toLowerCase().includes(needle) || citation.key.toLowerCase().includes(needle);
  });

  useEffect(() => {
    valueRef.current = value;
    setDraft(value);
    setSaveState("saved");
    if (viewRef.current && viewRef.current.state.doc.toString() !== value) {
      viewRef.current.dispatch({
        changes: { from: 0, to: viewRef.current.state.doc.length, insert: value },
      });
    }
  }, [value, fileRef]);

  useEffect(() => {
    commandRegistry.register({ id: "editor.toggle-mode", title: "Toggle Markdown editor mode", run: () => setMode((current) => nextEditorMode(current)) });
    commandRegistry.register({ id: "editor.insert-citation", title: "Insert citation token", run: () => setPickerOpen(true) });
  }, []);

  useEffect(() => {
    setRuntimeSyncState(collaboration?.enabled ? collaboration.syncState : "offline");
  }, [collaboration?.enabled, collaboration?.syncState]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const lineSeparator = draft.includes("\r\n") ? "\r\n" : "\n";
    const collaborationExtensions = buildCollaborationExtensions({
      collaboration,
      draft,
      onRemoteDocument: (next) => {
        valueRef.current = next;
        setDraft(next);
        onChange(next);
      },
      onSyncState: setRuntimeSyncState,
      ref: collaborationRef,
    });
    const view = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: draft,
        extensions: [
          EditorState.lineSeparator.of(lineSeparator),
          history(),
          markdown(),
          syntaxHighlighting(defaultHighlightStyle),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          ...collaborationExtensions,
          hydraDecorationPlugin({ notes, citations, highlights, suggestions, onAcceptSuggestion, onRejectSuggestion }),
          EditorView.lineWrapping,
          EditorView.domEventHandlers({
            blur: () => {
              void persistDraft(view.state.doc.toString());
              return false;
            },
            keydown: (_event, activeView) => {
              const event = _event as KeyboardEvent;
              if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
                event.preventDefault();
                void persistDraft(activeView.state.doc.toString());
                return true;
              }
              if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "e") {
                event.preventDefault();
                setMode((current) => nextEditorMode(current));
                return true;
              }
              if (event.key === "@") {
                setPickerOpen(true);
              }
              return false;
            },
          }),
          EditorView.updateListener.of((update) => {
            if (!update.docChanged) return;
            const started = performance.now();
            const next = update.state.doc.toString();
            valueRef.current = next;
            lastEditAtRef.current = Date.now();
            setDraft(next);
            setSaveState("dirty");
            onChange(next);
            requestAnimationFrame(() => setLastLatencyMs(Math.round(performance.now() - started)));
          }),
        ],
      }),
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      collaborationRef.current?.socket?.close();
      collaborationRef.current?.doc.destroy();
      collaborationRef.current = null;
      viewRef.current = null;
    };
  }, [fileRef, notes, citations, highlights, suggestions, collaboration?.enabled, collaboration?.documentId, collaboration?.projectId]);

  useEffect(() => {
    if (saveState !== "dirty") return;
    const id = window.setInterval(() => {
      const elapsedMs = Date.now() - lastEditAtRef.current;
      const state = recoverableAutosaveState({ dirty: saveState === "dirty", focused: document.activeElement?.closest(".cm-editor") != null, elapsedMs });
      if (state.shouldSave) {
        void persistDraft(valueRef.current);
      }
    }, 500);
    return () => window.clearInterval(id);
  }, [saveState]);

  function setModeWithAnnouncement(next: EditorMode) {
    setMode(next);
  }

  async function persistDraft(content: string) {
    if (saveState === "saving") return;
    setSaveState("saving");
    try {
      await onSave(content);
      setSaveState("saved");
    } catch (error) {
      console.error(error);
      setSaveState("failed");
    }
  }

  function onAcceptSuggestion(suggestion: InlineSuggestion) {
    if (trustOrigin === "untrusted") return;
    const current = viewRef.current?.state.doc.toString() ?? draft;
    const next = applyInlineSuggestion(current, suggestion, "accept");
    viewRef.current?.dispatch({ changes: { from: 0, to: current.length, insert: next } });
  }

  function onRejectSuggestion(_suggestion: InlineSuggestion) {
    setSaveState((current) => current);
  }

  function insertCitation(citation: CitationOption) {
    const view = viewRef.current;
    if (!view) return;
    const cursor = view.state.selection.main.from;
    const result = insertCitationToken(view.state.doc.toString(), cursor, citation.key);
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: result.content },
      selection: { anchor: result.cursor },
    });
    setPickerOpen(false);
    setPickerQuery("");
    view.focus();
  }

  const selectionContext = viewRef.current
    ? buildSelectionContext({
        fileRef,
        content: draft,
        from: viewRef.current.state.selection.main.from,
        to: viewRef.current.state.selection.main.to,
        mode,
      })
    : buildSelectionContext({ fileRef, content: draft, from: 0, to: 0, mode });

  (window as Window & { hydraMarkdownSelection?: typeof buildSelectionContext }).hydraMarkdownSelection = () => selectionContext;

  const canShowEditor = mode === "source" || mode === "split" || mode === "live";
  const canShowPreview = mode === "live" || mode === "split";
  const syncState = collaboration?.enabled ? runtimeSyncState : "offline";
  const presence = collaboration?.enabled ? collaboration.remoteUsers : [];

  return (
    <div className="markdown-editor-shell" data-editor-mode={mode}>
      <div className="markdown-toolbar" role="toolbar" aria-label="Markdown editor toolbar">
        <div className="mode-segment" aria-label="Editor mode">
          {(["live", "source", "split"] as EditorMode[]).map((option) => (
            <button
              key={option}
              className={mode === option ? "active" : ""}
              onClick={() => setModeWithAnnouncement(option)}
              aria-pressed={mode === option}
              title={`${option} mode`}
            >
              {option === "live" ? <Eye size={14} /> : option === "source" ? <Code2 size={14} /> : <Columns2 size={14} />}
              <span>{option}</span>
            </button>
          ))}
        </div>
        <button onClick={() => setPickerOpen(true)}>
          <Quote size={14} /> Cite
        </button>
        <button onClick={() => void persistDraft(viewRef.current?.state.doc.toString() ?? draft)}>
          <Save size={14} /> Save
        </button>
        <span className={`save-indicator ${saveState}`} aria-live="polite">
          {saveState === "dirty" ? "unsaved" : saveState}
        </span>
        <span className={`sync-indicator ${syncState}`} aria-live="polite">
          {syncState === "offline" ? <WifiOff size={13} /> : <Users size={13} />}
          {syncState}
        </span>
        {lastLatencyMs !== null && <span className="latency-indicator">{lastLatencyMs} ms</span>}
      </div>

      {pickerOpen && (
        <div className="citation-picker" role="dialog" aria-label="Citation picker">
          <input value={pickerQuery} onChange={(event) => setPickerQuery(event.target.value)} placeholder="Search title, author, year, DOI or key" autoFocus />
          {citations.length === 0 ? (
            <div className="picker-state">No sources yet. Import or add a source to cite while writing.</div>
          ) : filteredCitations.length === 0 ? (
            <div className="picker-state">No matches</div>
          ) : (
            filteredCitations.map((citation) => (
              <button key={citation.key} onClick={() => insertCitation(citation)}>
                <strong>{citation.title}</strong>
                <span>[@{citation.key}]</span>
              </button>
            ))
          )}
        </div>
      )}

      <div className="markdown-editor-grid">
        {canShowEditor && <div ref={hostRef} className={mode === "live" ? "editor-pane live" : "editor-pane"} aria-label="CodeMirror 6 Markdown editor" />}
        {canShowPreview && <article className="markdown-preview" dangerouslySetInnerHTML={{ __html: preview }} aria-label="Markdown live preview" />}
      </div>

      <div className="selection-context" aria-label="Selection context">
        <span>{selectionContext.fileRef}</span>
        <span>
          {selectionContext.selection.from}:{selectionContext.selection.to}
        </span>
        {trustOrigin === "untrusted" && <span className="status-pill warning">untrusted text routes edits to Review Inbox</span>}
        {presence.length > 0 && (
          <span className="presence-list" aria-label="Remote collaborators">
            {presence.map((user) => user.displayName).join(", ")}
          </span>
        )}
      </div>
    </div>
  );
}

function buildCollaborationExtensions({
  collaboration,
  draft,
  onRemoteDocument,
  onSyncState,
  ref,
}: {
  collaboration: CollaborationConfig | undefined;
  draft: string;
  onRemoteDocument: (value: string) => void;
  onSyncState: (state: SyncState) => void;
  ref: React.MutableRefObject<{ doc: Y.Doc; awareness: LocalAwareness; socket: WebSocket | null } | null>;
}) {
  if (!collaboration?.enabled) return [];
  const doc = new Y.Doc();
  const ytext = doc.getText("markdown");
  ytext.insert(0, draft);
  const awareness = new LocalAwareness(doc);
  const displayName = window.localStorage.getItem("hydra:collaboration:displayName") || "Local researcher";
  awareness.setLocalStateField("user", { name: displayName, color: "#2f81f7", colorLight: "rgba(47, 129, 247, 0.18)" });
  for (const [index, user] of collaboration.remoteUsers.entries()) {
    const cursor = Y.createRelativePositionFromTypeIndex(ytext, 0);
    awareness.setRemoteState(10_000 + index, {
      user: { name: user.displayName, color: user.color || "#3fb950", colorLight: "rgba(63, 185, 80, 0.18)" },
      cursor: { anchor: cursor, head: cursor },
    });
  }
  const socket = openCollaborationSocket(collaboration, doc, onRemoteDocument, onSyncState);
  ref.current = { doc, awareness, socket };
  return [yCollab(ytext, awareness, { undoManager: new Y.UndoManager(ytext) })];
}

function openCollaborationSocket(
  collaboration: CollaborationConfig,
  doc: Y.Doc,
  onRemoteDocument: (value: string) => void,
  onSyncState: (state: SyncState) => void,
) {
  const token = window.localStorage.getItem("hydra:collaboration:sessionToken");
  if (!token) {
    onSyncState("offline");
    return null;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = new URL(`/api/collaboration/ws/${encodeURIComponent(collaboration.projectId)}/${encodeURIComponent(collaboration.documentId)}`, window.location.href);
  url.protocol = protocol;
  url.searchParams.set("token", token);
  const socket = new WebSocket(url);
  onSyncState("connecting");
  socket.addEventListener("open", () => onSyncState("syncing"));
  socket.addEventListener("close", () => onSyncState("offline"));
  socket.addEventListener("error", () => onSyncState("offline"));
  doc.on("update", (update: Uint8Array) => {
    if (socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ type: "document-update", update: bytesToBase64(update) }));
  });
  socket.addEventListener("message", (event) => {
    try {
      const payload = JSON.parse(String(event.data)) as { type?: string; update?: string; content?: string };
      if (payload.type === "document-update" && payload.update) {
        Y.applyUpdate(doc, base64ToBytes(payload.update));
        onRemoteDocument(doc.getText("markdown").toString());
        onSyncState("synced");
      }
      if (payload.type === "document-snapshot" && typeof payload.content === "string") {
        const ytext = doc.getText("markdown");
        ytext.delete(0, ytext.length);
        ytext.insert(0, payload.content);
        onRemoteDocument(payload.content);
        onSyncState("synced");
      }
      if (payload.type === "presence") {
        onSyncState("synced");
      }
    } catch (error) {
      console.error(error);
    }
  });
  return socket;
}

class LocalAwareness {
  readonly doc: Y.Doc;
  private localState: Record<string, unknown> = {};
  private readonly states = new Map<number, Record<string, unknown>>();
  private readonly listeners = new Set<(change: { added: number[]; updated: number[]; removed: number[] }) => void>();

  constructor(doc: Y.Doc) {
    this.doc = doc;
    this.states.set(doc.clientID, this.localState);
  }

  getLocalState() {
    return this.localState;
  }

  setLocalStateField(field: string, value: unknown) {
    this.localState = { ...this.localState, [field]: value };
    this.states.set(this.doc.clientID, this.localState);
    this.emit({ added: [], updated: [this.doc.clientID], removed: [] });
  }

  setRemoteState(clientId: number, state: Record<string, unknown>) {
    const added = this.states.has(clientId) ? [] : [clientId];
    const updated = this.states.has(clientId) ? [clientId] : [];
    this.states.set(clientId, state);
    this.emit({ added, updated, removed: [] });
  }

  getStates() {
    return this.states;
  }

  on(_event: "change", listener: (change: { added: number[]; updated: number[]; removed: number[] }) => void) {
    this.listeners.add(listener);
  }

  off(_event: "change", listener: (change: { added: number[]; updated: number[]; removed: number[] }) => void) {
    this.listeners.delete(listener);
  }

  private emit(change: { added: number[]; updated: number[]; removed: number[] }) {
    for (const listener of this.listeners) listener(change);
  }
}

function bytesToBase64(bytes: Uint8Array) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64ToBytes(value: string) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

function hydraDecorationPlugin({
  notes,
  citations,
  highlights,
  suggestions,
  onAcceptSuggestion,
  onRejectSuggestion,
}: {
  notes: NoteOption[];
  citations: CitationOption[];
  highlights: TextHighlight[];
  suggestions: InlineSuggestion[];
  onAcceptSuggestion: (suggestion: InlineSuggestion) => void;
  onRejectSuggestion: (suggestion: InlineSuggestion) => void;
}) {
  return ViewPlugin.fromClass(
    class {
      decorations: DecorationSet;

      constructor(view: EditorView) {
        this.decorations = buildDecorations(view, notes, citations, highlights, suggestions, onAcceptSuggestion, onRejectSuggestion);
      }

      update(update: ViewUpdate) {
        if (update.docChanged || update.viewportChanged) {
          this.decorations = buildDecorations(update.view, notes, citations, highlights, suggestions, onAcceptSuggestion, onRejectSuggestion);
        }
      }
    },
    {
      decorations: (plugin) => plugin.decorations,
    },
  );
}

function buildDecorations(
  view: EditorView,
  notes: NoteOption[],
  citations: CitationOption[],
  highlights: TextHighlight[],
  suggestions: InlineSuggestion[],
  onAcceptSuggestion: (suggestion: InlineSuggestion) => void,
  onRejectSuggestion: (suggestion: InlineSuggestion) => void,
) {
  const markdown = view.state.doc.toString();
  const ranges: Range<Decoration>[] = [];
  const decorations = decorateMarkdown(markdown, { notes, citations });
  for (const item of decorations) {
    if (item.kind === "callout") {
      const line = view.state.doc.lineAt(item.from);
      ranges.push(Decoration.line({ class: `cm-hydra-callout cm-hydra-callout-${item.calloutType}` }).range(line.from));
    } else if (item.kind === "wikilink") {
      ranges.push(Decoration.mark({ class: item.resolved ? "cm-hydra-wikilink" : "cm-hydra-wikilink dangling" }).range(item.from, item.to));
    } else {
      ranges.push(Decoration.mark({ class: item.resolved ? "cm-hydra-citation" : "cm-hydra-citation dangling" }).range(item.from, item.to));
    }
  }
  for (const highlight of highlights) {
    ranges.push(Decoration.mark({ class: `cm-hydra-${highlight.type}-highlight` }).range(highlight.from, highlight.to));
  }
  for (const suggestion of suggestions) {
    ranges.push(Decoration.mark({ class: "cm-hydra-suggestion" }).range(suggestion.from, suggestion.to));
    ranges.push(
      Decoration.widget({
        side: 1,
        widget: new SuggestionActionsWidget(suggestion, onAcceptSuggestion, onRejectSuggestion),
      }).range(suggestion.to),
    );
  }
  return Decoration.set(ranges, true);
}

class SuggestionActionsWidget extends WidgetType {
  constructor(
    private readonly suggestion: InlineSuggestion,
    private readonly onAccept: (suggestion: InlineSuggestion) => void,
    private readonly onReject: (suggestion: InlineSuggestion) => void,
  ) {
    super();
  }

  toDOM() {
    const wrap = document.createElement("span");
    wrap.className = "cm-suggestion-actions";
    const accept = document.createElement("button");
    accept.type = "button";
    accept.ariaLabel = "Accept suggestion";
    accept.innerHTML = CheckIcon;
    accept.addEventListener("click", () => this.onAccept(this.suggestion));
    const reject = document.createElement("button");
    reject.type = "button";
    reject.ariaLabel = "Reject suggestion";
    reject.innerHTML = XIcon;
    reject.addEventListener("click", () => this.onReject(this.suggestion));
    wrap.append(accept, reject);
    return wrap;
  }
}

const CheckIcon = `<svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><path fill="currentColor" d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/></svg>`;
const XIcon = `<svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><path fill="currentColor" d="m18.3 5.7-1.4-1.4L12 9.2 7.1 4.3 5.7 5.7l4.9 4.9-4.9 4.9 1.4 1.4 4.9-4.9 4.9 4.9 1.4-1.4-4.9-4.9z"/></svg>`;
