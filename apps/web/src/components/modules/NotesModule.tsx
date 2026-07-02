import React from "react";
import { Search, FileText, X } from "lucide-react";
import { useAppContext, Note } from "../../core/context";
import { registry } from "../../core/registry";
import { HydraMarkdownEditor } from "../editor/HydraMarkdownEditor";

export function LocalGraphView({
  activeNode,
  neighbors,
  onNodeClick
}: {
  activeNode: { id: string; title: string; type?: string };
  neighbors: any[];
  onNodeClick: (nodeId: string, nodeType: string) => void;
}) {
  const width = 300;
  const height = 240;
  const cx = width / 2;
  const cy = height / 2;
  const r = 80;

  const getColors = (type: string) => {
    switch (type) {
      case "note": return { fill: "#8b5cf6", stroke: "#a78bfa" };
      case "source": return { fill: "#10b981", stroke: "#34d399" };
      case "task": return { fill: "#f59e0b", stroke: "#fbbf24" };
      case "claim": return { fill: "#f43f5e", stroke: "#fb7185" };
      default: return { fill: "#0ea5e9", stroke: "#38bdf8" };
    }
  };

  const centerColor = getColors(activeNode.type || "note");

  return (
    <svg 
      width="100%" 
      height="240" 
      viewBox={`0 0 ${width} ${height}`} 
      style={{ 
        background: "var(--bg-dark)", 
        borderRadius: "8px", 
        border: "1px solid var(--border)" 
      }}
    >
      {neighbors.map((node, i) => {
        const angle = (i * 2 * Math.PI) / neighbors.length;
        const nx = cx + r * Math.cos(angle);
        const ny = cy + r * Math.sin(angle);
        return (
          <line
            key={`line-${node.id}`}
            x1={cx}
            y1={cy}
            x2={nx}
            y2={ny}
            stroke="var(--border)"
            strokeWidth="1.5"
            strokeDasharray="3 3"
          />
        );
      })}

      <g style={{ cursor: "default" }}>
        <circle
          cx={cx}
          cy={cy}
          r="16"
          fill={centerColor.fill}
          stroke={centerColor.stroke}
          strokeWidth="2.5"
        />
        <text
          x={cx}
          y={cy + 4}
          textAnchor="middle"
          fill="white"
          fontSize="9"
          fontWeight="bold"
        >
          ★
        </text>
      </g>

      {neighbors.map((node, i) => {
        const angle = (i * 2 * Math.PI) / neighbors.length;
        const nx = cx + r * Math.cos(angle);
        const ny = cy + r * Math.sin(angle);
        const colors = getColors(node.type);
        const isClickable = node.type === "note";

        return (
          <g
            key={`node-${node.id}`}
            onClick={() => isClickable && onNodeClick(node.id, node.type)}
            style={{ cursor: isClickable ? "pointer" : "default" }}
          >
            <circle
              cx={nx}
              cy={ny}
              r="10"
              fill={colors.fill}
              stroke={colors.stroke}
              strokeWidth="1.5"
            />
            <text
              x={nx}
              y={ny + 18}
              textAnchor="middle"
              fill="var(--fg)"
              fontSize="9"
              fontWeight="500"
              style={{ pointerEvents: "none" }}
            >
              {node.title.length > 10 ? node.title.substring(0, 8) + "..." : node.title}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function NotesSidebar() {
  const {
    notes,
    notesQuery,
    setNotesQuery,
    selectedNote,
    selectNote,
    createNewNote
  } = useAppContext();

  return (
    <div style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "12px", height: "100%", boxSizing: "border-box" }}>
      <div style={{ display: "flex", gap: "8px" }}>
        <div style={{ position: "relative", flex: 1 }}>
          <Search size={14} style={{ position: "absolute", left: "8px", top: "10px", color: "var(--fg-dim)" }} />
          <input
            type="text"
            value={notesQuery}
            onChange={(e) => setNotesQuery(e.target.value)}
            placeholder="Search notes..."
            style={{
              width: "100%",
              padding: "8px 8px 8px 28px",
              borderRadius: "4px",
              border: "1px solid var(--border)",
              backgroundColor: "var(--bg-dark)",
              color: "var(--fg)",
              fontSize: "13px",
              boxSizing: "border-box"
            }}
          />
        </div>
        <button
          onClick={createNewNote}
          style={{
            padding: "8px 12px",
            background: "var(--accent)",
            color: "white",
            borderRadius: "4px",
            border: "none",
            cursor: "pointer",
            fontSize: "13px",
            fontWeight: "bold"
          }}
        >
          +
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "8px" }}>
        {notes.length === 0 ? (
          <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
            <p style={{ color: "var(--fg-dim)", fontSize: "13px" }}>No notes found.</p>
          </div>
        ) : (
          notes.map(n => (
            <div
              key={n.id}
              onClick={() => selectNote(n)}
              style={{
                padding: "10px",
                backgroundColor: selectedNote?.id === n.id ? "var(--bg-lighter)" : "var(--bg-dark)",
                borderRadius: "6px",
                border: selectedNote?.id === n.id ? "1px solid var(--accent)" : "1px solid var(--border)",
                cursor: "pointer",
                transition: "all 0.2s"
              }}
            >
              <div style={{ fontWeight: "bold", fontSize: "13px", color: "var(--fg)" }}>{n.title}</div>
              <div style={{ fontSize: "11px", color: "var(--fg-dim)", marginTop: "4px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {n.body}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export function NotesMain() {
  const {
    notes,
    selectedNote,
    setSelectedNote,
    noteLinks,
    sources,
    selectNote,
    fetchNotes,
    fetchNoteLinks,
    deleteNote
  } = useAppContext();

  if (!selectedNote) {
    return (
      <div className="empty-state">
        <FileText />
        <h2>Notes</h2>
        <p>Write your synthesis here. Select a note from the sidebar or click "+" to create a new one.</p>
      </div>
    );
  }
  const activeNote = selectedNote;

  async function saveNoteContent(body: string) {
    const payload: Note = { ...activeNote, body };
    setSelectedNote(payload);
    const res = await fetch(`/api/notes/${activeNote.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: activeNote.title,
        body,
        source_id: activeNote.source_id
      })
    });
    if (!res.ok) {
      throw new Error("Failed to save note");
    }
    const data = await res.json();
    setSelectedNote(data);
    await fetchNotes();
    await fetchNoteLinks(data.id);
  }

  const citationOptions = sources.map((source, index) => ({
    key: source.citation_key || source.metadata_json?.citation_key || source.id || `source${index + 1}`,
    sourceId: source.id,
    title: source.title,
  }));

  const noteOptions = notes.map((note) => ({ id: note.id, title: note.title }));
  const claimText = "Self-attention replaces recurrence entirely";
  const evidenceText = "Use [[Attention Is All You Need]]";
  const claimStart = activeNote.body.indexOf(claimText);
  const evidenceStart = activeNote.body.indexOf(evidenceText);
  const highlights = [
    ...(claimStart >= 0 ? [{ id: "claim-inline", type: "claim" as const, from: claimStart, to: claimStart + claimText.length }] : []),
    ...(evidenceStart >= 0 ? [{ id: "evidence-inline", type: "evidence" as const, from: evidenceStart, to: evidenceStart + evidenceText.length }] : []),
  ];
  const suggestionStart = activeNote.body.indexOf("Use ");
  const suggestions = suggestionStart >= 0
    ? [{ id: "suggestion-passive", from: suggestionStart, to: suggestionStart + 3, replacement: "Compare" }]
    : [];

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden", width: "100%" }}>
      {/* Editor side */}
      <div style={{ flex: 1, borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", background: "var(--bg-dark)", height: "100%" }}>
        <div style={{ padding: "12px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px" }}>
          <input
            type="text"
            value={activeNote.title}
            onChange={(e) => setSelectedNote({ ...activeNote, title: e.target.value })}
            placeholder="Note Title"
            style={{
              flex: 1,
              padding: "6px 10px",
              background: "var(--bg)",
              color: "var(--fg)",
              border: "1px solid var(--border)",
              borderRadius: "4px",
              fontSize: "15px",
              fontWeight: "bold"
            }}
          />
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              onClick={() => void saveNoteContent(activeNote.body)}
              style={{
                padding: "6px 12px",
                background: "var(--accent)",
                color: "white",
                borderRadius: "4px",
                border: "none",
                cursor: "pointer",
                fontSize: "13px",
                fontWeight: "bold"
              }}
            >
              Save
            </button>
            <button
              onClick={() => deleteNote(activeNote.id)}
              style={{
                padding: "6px 12px",
                background: "transparent",
                color: "#ef4444",
                border: "1px solid #ef4444",
                borderRadius: "4px",
                cursor: "pointer",
                fontSize: "13px",
                fontWeight: "bold"
              }}
            >
              Delete
            </button>
          </div>
        </div>
        <HydraMarkdownEditor
          fileRef={activeNote.relative_path || `knowledge/${activeNote.title}.md`}
          value={activeNote.body}
          notes={noteOptions}
          citations={citationOptions}
          highlights={highlights}
          suggestions={suggestions}
          trustOrigin={activeNote.trust_origin || "user"}
          onChange={(body) => setSelectedNote({ ...activeNote, body })}
          onSave={saveNoteContent}
        />
      </div>

      {/* Obsidian sidebar / graph side */}
      <div style={{ width: "320px", display: "flex", flexDirection: "column", background: "var(--bg)", overflowY: "auto", borderLeft: "1px solid var(--border)", height: "100%" }}>
        <div style={{ padding: "12px", borderBottom: "1px solid var(--border)", fontWeight: "bold", fontSize: "12px", color: "var(--fg-dim)", letterSpacing: "0.5px" }}>
          KNOWLEDGE GRAPH & LINKS
        </div>

        <div style={{ padding: "16px" }}>
          <LocalGraphView
            activeNode={{ id: activeNote.id, title: activeNote.title, type: "note" }}
            neighbors={[
              ...noteLinks.backlinks.map(l => ({ ...l, type: l.type || "note" })),
              ...noteLinks.forward.map(l => ({ ...l, type: l.type || "note" }))
            ].filter((v, i, a) => a.findIndex(t => t.id === v.id) === i)}
            onNodeClick={(nodeId) => {
              const found = notes.find(n => n.id === nodeId);
              if (found) {
                selectNote(found);
              } else {
                fetch(`/api/notes/${nodeId}`)
                  .then(r => r.json())
                  .then(n => selectNote(n))
                  .catch(console.error);
              }
            }}
          />
        </div>

        {/* Backlinks list */}
        <div style={{ padding: "12px 16px", borderTop: "1px solid var(--border)" }}>
          <div style={{ fontWeight: "bold", fontSize: "11px", color: "var(--fg-dim)", marginBottom: "8px", letterSpacing: "0.5px" }}>
            BACKLINKS ({noteLinks.backlinks.length})
          </div>
          {noteLinks.backlinks.length === 0 ? (
            <div style={{ fontSize: "12px", color: "var(--fg-dim)", fontStyle: "italic" }}>
              No backlinks to this note.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {noteLinks.backlinks.map(link => (
                <div
                  key={link.id}
                  onClick={() => {
                    if (link.type === "note") {
                      const found = notes.find(n => n.id === link.id);
                      if (found) {
                        selectNote(found);
                      } else {
                        fetch(`/api/notes/${link.id}`)
                          .then(r => r.json())
                          .then(n => selectNote(n))
                          .catch(console.error);
                      }
                    }
                  }}
                  style={{
                    padding: "6px 8px",
                    background: "var(--bg-dark)",
                    borderRadius: "4px",
                    fontSize: "12px",
                    border: "1px solid var(--border)",
                    cursor: link.type === "note" ? "pointer" : "default",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center"
                  }}
                >
                  <span style={{ fontWeight: "500", color: "var(--fg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "180px" }}>{link.title}</span>
                  <span style={{
                    fontSize: "10px",
                    padding: "2px 4px",
                    borderRadius: "3px",
                    background: link.type === "note" ? "rgba(139, 92, 246, 0.15)" : "rgba(16, 185, 129, 0.15)",
                    color: link.type === "note" ? "#a78bfa" : "#34d399"
                  }}>
                    {link.type}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Outward / Forward links list */}
        <div style={{ padding: "12px 16px", borderTop: "1px solid var(--border)" }}>
          <div style={{ fontWeight: "bold", fontSize: "11px", color: "var(--fg-dim)", marginBottom: "8px", letterSpacing: "0.5px" }}>
            OUTWARD LINKS ({noteLinks.forward.length})
          </div>
          {noteLinks.forward.length === 0 ? (
            <div style={{ fontSize: "12px", color: "var(--fg-dim)", fontStyle: "italic" }}>
              No outward links inside this note.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {noteLinks.forward.map(link => (
                <div
                  key={link.id}
                  onClick={() => {
                    if (link.type === "note") {
                      const found = notes.find(n => n.id === link.id);
                      if (found) {
                        selectNote(found);
                      } else {
                        fetch(`/api/notes/${link.id}`)
                          .then(r => r.json())
                          .then(n => selectNote(n))
                          .catch(console.error);
                      }
                    }
                  }}
                  style={{
                    padding: "6px 8px",
                    background: "var(--bg-dark)",
                    borderRadius: "4px",
                    fontSize: "12px",
                    border: "1px solid var(--border)",
                    cursor: link.type === "note" ? "pointer" : "default",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center"
                  }}
                >
                  <span style={{ fontWeight: "500", color: "var(--fg)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "180px" }}>{link.title}</span>
                  <span style={{
                    fontSize: "10px",
                    padding: "2px 4px",
                    borderRadius: "3px",
                    background: link.type === "note" ? "rgba(139, 92, 246, 0.15)" : "rgba(16, 185, 129, 0.15)",
                    color: link.type === "note" ? "#a78bfa" : "#34d399"
                  }}>
                    {link.type}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Register components
registry.register("hydra.notes", NotesSidebar);
registry.register("hydra.notes.main", NotesMain);
