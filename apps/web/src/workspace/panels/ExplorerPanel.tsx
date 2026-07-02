import { useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronRight, FileText, Folder, Library, Plus, RefreshCcw, ToggleLeft, ToggleRight } from "lucide-react";
import type { PanelComponentProps } from "../panelRegistry";
import { useWorkspaceData } from "../data";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";
import type { ProjectObjectsResponse, ProjectTreeNode } from "../../lib/api";

type ExplorerMode = "curated" | "raw";
type ExplorerRow =
  | { key: string; depth: number; type: "group"; title: string; count: number }
  | { key: string; depth: number; type: "note" | "source" | "claim" | "task" | "citation" | "raw"; title: string; subtitle?: string; indexStatus?: string; node?: ProjectTreeNode; id?: string };

export function ExplorerPanel({ openPanel, announce }: PanelComponentProps) {
  const { objects, tree, refreshAll } = useWorkspaceData();
  const [mode, setMode] = useState<ExplorerMode>(() => (localStorage.getItem("hydralab-explorer-mode") as ExplorerMode | null) ?? "curated");
  const parentRef = useRef<HTMLDivElement>(null);

  const rows = useMemo(() => {
    if (mode === "raw") return flattenRawTree(tree.data?.nodes ?? []);
    return flattenCuratedObjects(objects.data);
  }, [mode, objects.data, tree.data]);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 30,
    overscan: 12,
  });

  const loading = (mode === "curated" && objects.status === "loading" && !objects.data) || (mode === "raw" && tree.status === "loading" && !tree.data);
  const failure = mode === "curated" ? objects.status === "failure" ? objects.error : null : tree.status === "failure" ? tree.error : null;

  if (loading) return <LoadingState title="Loading explorer" />;
  if (failure) return <FailureState error={failure} onRetry={refreshAll} />;

  return (
    <PanelScaffold title="Explorer">
      <header className="panel-toolbar">
        <button
          onClick={() => {
            const next = mode === "curated" ? "raw" : "curated";
            localStorage.setItem("hydralab-explorer-mode", next);
            setMode(next);
          }}
        >
          {mode === "curated" ? <ToggleLeft size={14} /> : <ToggleRight size={14} />}
          {mode === "curated" ? "Curated" : "Raw"}
        </button>
        <button onClick={refreshAll}>
          <RefreshCcw size={14} /> Rescan
        </button>
        <button onClick={() => openPanel("markdown-editor")}>
          <Plus size={14} /> New note
        </button>
      </header>

      {rows.length === 0 ? (
        <EmptyState
          title={mode === "curated" ? "No sources yet" : "No files found"}
          message={mode === "curated" ? "The curated research explorer is empty because the backend has no notes, sources, claims, citations or tasks." : "The backend returned an empty project tree."}
          action={mode === "curated" ? "Discover sources" : "Open curated explorer"}
          onAction={() => (mode === "curated" ? openPanel("source-discovery") : setMode("curated"))}
        />
      ) : (
        <div ref={parentRef} className="virtual-tree" aria-label={`${mode} explorer`}>
          <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const row = rows[virtualRow.index];
              return (
                <button
                  key={row.key}
                  className={`tree-row ${row.type}`}
                  style={{ transform: `translateY(${virtualRow.start}px)`, paddingLeft: 8 + row.depth * 14 }}
                  onDoubleClick={() => openRow(row, openPanel, announce)}
                >
                  {iconForRow(row)}
                  <span>{row.title}</span>
                  {row.type === "group" && <small>{row.count}</small>}
                  {"indexStatus" in row && row.indexStatus && <small className={`status-pill ${row.indexStatus}`}>{row.indexStatus}</small>}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </PanelScaffold>
  );
}

export function flattenCuratedObjects(data: ProjectObjectsResponse | null | undefined): ExplorerRow[] {
  if (!data) return [];
  const groups: Array<[string, ExplorerRow[]]> = [
    [
      "Sources",
      data.objects.sources
        .filter((source) => !source.trashed)
        .map((source) => ({ key: `source:${source.id}`, type: "source" as const, depth: 1, title: source.title, subtitle: source.url, id: source.id })),
    ],
    [
      "Notes",
      data.objects.notes.map((note) => ({ key: `note:${note.id}`, type: "note" as const, depth: 1, title: note.title, subtitle: note.relative_path, id: note.id })),
    ],
    [
      "Claims",
      data.objects.claims.map((claim) => ({ key: `claim:${claim.id}`, type: "claim" as const, depth: 1, title: claim.text, subtitle: claim.status, id: claim.id })),
    ],
    [
      "Tasks",
      data.objects.tasks.map((task) => ({ key: `task:${task.id}`, type: "task" as const, depth: 1, title: task.title, subtitle: task.column, id: task.id })),
    ],
    [
      "Citations",
      data.objects.citations.map((citation) => ({ key: `citation:${citation.id}`, type: "citation" as const, depth: 1, title: citation.text, subtitle: citation.source_id, id: citation.id })),
    ],
  ];
  return groups.flatMap(([title, children]) => [{ key: `group:${title}`, type: "group" as const, depth: 0, title, count: children.length }, ...children]);
}

export function flattenRawTree(nodes: ProjectTreeNode[]): ExplorerRow[] {
  return nodes.map((node) => ({
    key: `raw:${node.path}`,
    type: "raw" as const,
    depth: node.depth,
    title: node.name,
    subtitle: node.path,
    indexStatus: node.index_status,
    node,
  }));
}

function openRow(row: ExplorerRow, openPanel: PanelComponentProps["openPanel"], announce: PanelComponentProps["announce"]) {
  if (row.type === "note" && row.id) openPanel("markdown-editor", { noteId: row.id, title: row.title });
  if (row.type === "source" && row.id) openPanel("pdf-reader", { sourceId: row.id, title: row.title });
  if (row.type === "citation" || row.type === "claim") openPanel("citation-evidence", { objectId: row.id, objectType: row.type });
  if (row.type === "raw" && row.node?.path.endsWith(".md")) openPanel("markdown-editor", { fileRef: row.node.path, title: row.node.name });
  announce(`Opened ${row.title}`);
}

function iconForRow(row: ExplorerRow) {
  if (row.type === "group") return <ChevronRight size={13} aria-hidden />;
  if (row.type === "source") return <Library size={13} aria-hidden />;
  if (row.type === "raw" && row.node?.type === "directory") return <Folder size={13} aria-hidden />;
  return <FileText size={13} aria-hidden />;
}
