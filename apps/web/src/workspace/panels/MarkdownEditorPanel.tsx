import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { HydraMarkdownEditor } from "../../components/editor/HydraMarkdownEditor";
import { api, type CitationRecord, type NoteRecord, type ProjectObjectsResponse } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { useWorkspaceData } from "../data";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";

export function MarkdownEditorPanel({ config, announce }: PanelComponentProps) {
  const { objects, review } = useWorkspaceData();
  const noteId = typeof config?.noteId === "string" ? config.noteId : null;
  const fileRef = typeof config?.fileRef === "string" ? config.fileRef : null;
  const [note, setNote] = useState<NoteRecord | null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(Boolean(noteId || fileRef));
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    void loadNote();
  }, [noteId, fileRef]);

  async function loadNote() {
    if (!noteId && !fileRef) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      if (noteId) {
        const loaded = await api.get<NoteRecord>(`/api/notes/${encodeURIComponent(noteId)}`);
        setNote(loaded);
        setContent(loaded.body ?? "");
      } else if (fileRef) {
        const loaded = await api.get<NoteRecord & { content?: string }>(`/api/note-files?path=${encodeURIComponent(fileRef)}`);
        setNote(loaded);
        setContent(loaded.content ?? loaded.body ?? "");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setLoading(false);
    }
  }

  async function createNote() {
    setError(null);
    try {
      const created = await api.post<NoteRecord>("/api/notes", { title: "Untitled note", body: "# Untitled note\n", source_id: null });
      setNote(created);
      setContent(created.body ?? "");
      objects.reload();
      announce("Created note");
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  async function save(nextContent: string) {
    if (!note) return;
    if (fileRef || note.relative_path) {
      await api.put(`/api/note-files/${encodeURIComponent(note.id)}`, { content: nextContent });
    } else {
      await api.put(`/api/notes/${encodeURIComponent(note.id)}`, { title: note.title, body: nextContent, source_id: note.source_id ?? null });
    }
    setContent(nextContent);
    review.reload();
  }

  if (loading) return <LoadingState title="Opening note" />;
  if (error) return <FailureState error={error} onRetry={loadNote} />;
  if (!note) {
    return (
      <EmptyState
        title="No note open"
        message="Open a note from Explorer or create a new Markdown note."
        action="New note"
        onAction={() => void createNote()}
      />
    );
  }

  return (
    <PanelScaffold title={note.title}>
      <header className="document-header">
        <strong>{note.title}</strong>
        <button onClick={() => void createNote()}>
          <Plus size={14} /> New note
        </button>
      </header>
      <HydraMarkdownEditor
        fileRef={note.relative_path || fileRef || note.id}
        value={content}
        notes={noteOptions(objects.data)}
        citations={citationOptions(objects.data)}
        onChange={setContent}
        onSave={save}
      />
    </PanelScaffold>
  );
}

function noteOptions(data: ProjectObjectsResponse | null | undefined) {
  return (data?.objects.notes ?? []).map((note) => ({ id: note.id, title: note.title }));
}

function citationOptions(data: ProjectObjectsResponse | null | undefined) {
  const sources = new Map((data?.objects.sources ?? []).map((source) => [source.id, source]));
  return (data?.objects.citations ?? []).map((citation: CitationRecord) => {
    const source = sources.get(citation.source_id);
    return {
      key: citation.citation_key || citation.source_id,
      sourceId: citation.source_id,
      title: source?.title || citation.text,
    };
  });
}
