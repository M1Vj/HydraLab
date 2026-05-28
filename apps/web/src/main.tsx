import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BookOpenCheck,
  CheckCircle2,
  FileText,
  Library,
  ListTodo,
  MessageSquareText,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Terminal,
  Activity,
  X,
  SplitSquareHorizontal
} from "lucide-react";

import "./styles.css";

type ActivityType = "chat" | "sources" | "notes" | "tasks" | "settings" | "evidence";

interface Message {
  id: string;
  role: string;
  content: string;
}

function LocalGraphView({ activeNode, neighbors, onNodeClick }: { activeNode: any; neighbors: any[]; onNodeClick: (nodeId: string, nodeType: string) => void }) {
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
    <svg width="100%" height="240" viewBox={`0 0 ${width} ${height}`} style={{ background: "var(--bg-dark)", borderRadius: "8px", border: "1px solid var(--border)" }}>
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

function App() {
  const [activeActivity, setActiveActivity] = useState<ActivityType>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [bottomPanelOpen, setBottomPanelOpen] = useState(true);
  const [activeEditorTab, setActiveEditorTab] = useState("research-1");
  const [draftText, setDraftText] = useState("");
  const [reviewData, setReviewData] = useState<any>(null);
  const [isReviewing, setIsReviewing] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [evidenceList, setEvidenceList] = useState<any[]>([]);

  const [notes, setNotes] = useState<any[]>([]);
  const [notesQuery, setNotesQuery] = useState("");
  const [selectedNote, setSelectedNote] = useState<any | null>(null);
  const [noteLinks, setNoteLinks] = useState<{ backlinks: any[]; forward: any[] }>({ backlinks: [], forward: [] });

  const fetchNotes = async (q = "") => {
    try {
      const res = await fetch(`http://localhost:8000/api/notes${q ? `?query=${encodeURIComponent(q)}` : ""}`);
      const data = await res.json();
      setNotes(data.notes || []);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchNoteLinks = async (noteId: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/notes/${noteId}/links`);
      const data = await res.json();
      setNoteLinks(data);
    } catch (err) {
      console.error(err);
    }
  };

  const selectNote = (note: any) => {
    setSelectedNote(note);
    fetchNoteLinks(note.id);
    setActiveEditorTab("notes-1");
  };

  const createNewNote = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "New Note",
          body: "Write your note here... Use [[Note Title]] to link notes together.",
          source_id: null
        })
      });
      const data = await res.json();
      fetchNotes(notesQuery);
      selectNote(data);
    } catch (err) {
      console.error(err);
    }
  };

  const saveNote = async () => {
    if (!selectedNote) return;
    try {
      const res = await fetch(`http://localhost:8000/api/notes/${selectedNote.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: selectedNote.title,
          body: selectedNote.body,
          source_id: selectedNote.source_id
        })
      });
      const data = await res.json();
      setSelectedNote(data);
      fetchNotes(notesQuery);
      fetchNoteLinks(data.id);
    } catch (err) {
      console.error(err);
    }
  };

  const deleteNote = async (noteId: string) => {
    try {
      await fetch(`http://localhost:8000/api/notes/${noteId}`, {
        method: "DELETE"
      });
      setSelectedNote(null);
      setNoteLinks({ backlinks: [], forward: [] });
      fetchNotes(notesQuery);
    } catch (err) {
      console.error(err);
    }
  };

  React.useEffect(() => {
    fetchNotes(notesQuery);
  }, [notesQuery]);

  React.useEffect(() => {
    if (activeActivity === "evidence") {
      fetch("http://localhost:8000/api/evidence")
        .then(r => r.json())
        .then(data => setEvidenceList(data.evidence || []))
        .catch(console.error);
    }
  }, [activeActivity]);


  const analyzeText = async () => {
    if (!draftText.trim()) return;
    setIsReviewing(true);
    try {
      const res = await fetch("http://localhost:8000/api/reviews/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: draftText })
      });
      const data = await res.json();
      setReviewData(data);
    } catch (err) {
      console.error(err);
    } finally {
      setIsReviewing(false);
    }
  };

  const sendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;
    const userMessage = { id: Date.now().toString(), role: "user", content: inputValue };
    setMessages(prev => [...prev, userMessage]);
    setInputValue("");
    setIsLoading(true);
    setStatusMessage("Starting request...");
    
    try {
      const res = await fetch("http://localhost:8000/api/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: inputValue, conversation_id: conversationId })
      });
      
      if (!res.body) return;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      
      let assistantMessage = { id: (Date.now() + 1).toString(), role: "assistant", content: "" };
      setMessages(prev => [...prev, assistantMessage]);
      
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split("\n\n");
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const dataStr = line.substring(6);
          if (!dataStr) continue;
          try {
            const data = JSON.parse(dataStr);
            if (data.type === "status") {
              setStatusMessage(data.content);
            } else if (data.type === "message") {
              assistantMessage.content += data.content;
              setMessages(prev => {
                const newMsgs = [...prev];
                newMsgs[newMsgs.length - 1] = { ...assistantMessage };
                return newMsgs;
              });
            } else if (data.type === "done") {
              setConversationId(data.conversation_id);
            }
          } catch (e) {
             console.error("Error parsing chunk", e, dataStr);
          }
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
      setStatusMessage("");
    }
  };

  const toggleSidebar = (activity: ActivityType) => {
    if (activeActivity === activity) {
      setSidebarOpen(!sidebarOpen);
    } else {
      setActiveActivity(activity);
      setSidebarOpen(true);
    }
  };

  return (
    <div className={`workbench ${!sidebarOpen ? "sidebar-closed" : "sidebar-open"}`}>
      
      {/* Activity Bar */}
      <nav className="activity-bar" aria-label="Activity Bar">
        <div 
          className={`activity-icon ${activeActivity === "chat" ? "active" : ""}`} 
          onClick={() => toggleSidebar("chat")}
          title="Research Chat"
        >
          <MessageSquareText size={24} strokeWidth={1.5} />
        </div>
        <div 
          className={`activity-icon ${activeActivity === "sources" ? "active" : ""}`} 
          onClick={() => toggleSidebar("sources")}
          title="Sources"
        >
          <Library size={24} strokeWidth={1.5} />
        </div>
        <div 
          className={`activity-icon ${activeActivity === "notes" ? "active" : ""}`} 
          onClick={() => toggleSidebar("notes")}
          title="Notes"
        >
          <FileText size={24} strokeWidth={1.5} />
        </div>
        <div 
          className={`activity-icon ${activeActivity === "tasks" ? "active" : ""}`} 
          onClick={() => toggleSidebar("tasks")}
          title="Tasks"
        >
          <ListTodo size={24} strokeWidth={1.5} />
        </div>
        <div 
          className={`activity-icon ${activeActivity === "evidence" ? "active" : ""}`} 
          onClick={() => toggleSidebar("evidence")}
          title="Evidence"
        >
          <ShieldCheck size={24} strokeWidth={1.5} />
        </div>
        <div style={{ flex: 1 }} />
        <div 
          className={`activity-icon ${activeActivity === "settings" ? "active" : ""}`} 
          onClick={() => toggleSidebar("settings")}
          title="Settings"
        >
          <Settings size={24} strokeWidth={1.5} />
        </div>
      </nav>

      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <span>{activeActivity.toUpperCase()}</span>
        </div>
        <div className="sidebar-content">
          {activeActivity === "chat" && (
            <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
              <p>No recent research chats.</p>
            </div>
          )}
          {activeActivity === "sources" && (
            <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
              <p>No sources uploaded.</p>
            </div>
          )}
          {activeActivity === "notes" && (
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
          )}
          {activeActivity === "tasks" && (
            <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
              <p>No active tasks.</p>
            </div>
          )}
          {activeActivity === "evidence" && (
            <div style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "12px" }}>
              {evidenceList.length === 0 ? (
                <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
                  <p>No evidence links found.</p>
                </div>
              ) : (
                evidenceList.map(ev => (
                  <div key={ev.id} style={{ 
                    padding: "12px", 
                    backgroundColor: "var(--bg-dark)", 
                    borderRadius: "6px",
                    borderLeft: ev.support === "unsupported" ? "4px solid #ef4444" : ev.support === "weak" ? "4px solid #f59e0b" : "4px solid #10b981"
                  }}>
                    <div style={{ fontSize: "13px", fontWeight: "bold", marginBottom: "4px", color: "var(--fg)" }}>{ev.claim_text}</div>
                    <div style={{ fontSize: "12px", color: "var(--fg-dim)", marginBottom: "8px", fontStyle: "italic" }}>"{ev.passage}"</div>
                    <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between", color: "var(--fg-dim)" }}>
                      <span>Source: {ev.source_title}</span>
                      <span style={{ 
                        color: ev.support === "unsupported" ? "#ef4444" : ev.support === "weak" ? "#f59e0b" : "#10b981"
                      }}>
                        {ev.support.toUpperCase()}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </aside>

      {/* Main Area */}
      <main className="main-area">
        <div className="editor-group">
          <div className="editor-tabs">
            <div 
              className={`editor-tab ${activeEditorTab === "research-1" ? "active" : ""}`}
              onClick={() => setActiveEditorTab("research-1")}
            >
              <Sparkles size={14} />
              Research Agent
              <X size={14} style={{ marginLeft: 8, opacity: 0.5 }} />
            </div>
            <div 
              className={`editor-tab ${activeEditorTab === "notes-1" ? "active" : ""}`}
              onClick={() => setActiveEditorTab("notes-1")}
            >
              <FileText size={14} />
              Draft Notes.md
              <X size={14} style={{ marginLeft: 8, opacity: 0.5 }} />
            </div>
            <div 
              className={`editor-tab ${activeEditorTab === "writing-1" ? "active" : ""}`}
              onClick={() => setActiveEditorTab("writing-1")}
            >
              <BookOpenCheck size={14} />
              Writing Review
              <X size={14} style={{ marginLeft: 8, opacity: 0.5 }} />
            </div>
            <div style={{ flex: 1 }} />
            <div className="editor-tab" style={{ border: "none", cursor: "default" }}>
              <SplitSquareHorizontal size={14} style={{ cursor: "pointer", opacity: 0.7 }} />
            </div>
          </div>

          <div className="editor-pane-container">
            <div className="editor-pane">
              {activeEditorTab === "research-1" && (
                <div className="chat-interface" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
                  <div className="chat-messages" style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
                    {messages.length === 0 ? (
                      <div className="empty-state">
                        <Sparkles />
                        <h2>Hydra Research</h2>
                        <p>Ask a question, upload a paper, or synthesize your notes. I will generate citations and trace claims back to their source.</p>
                      </div>
                    ) : (
                      messages.map(msg => (
                        <div key={msg.id} style={{ marginBottom: "20px", textAlign: msg.role === "user" ? "right" : "left" }}>
                          <div style={{
                            display: "inline-block",
                            padding: "10px 14px",
                            borderRadius: "8px",
                            backgroundColor: msg.role === "user" ? "var(--accent)" : "var(--bg-lighter)",
                            color: msg.role === "user" ? "white" : "inherit",
                            maxWidth: "80%"
                          }}>
                            {msg.content}
                          </div>
                        </div>
                      ))
                    )}
                    {isLoading && statusMessage && (
                      <div style={{ marginBottom: "20px", textAlign: "left", fontSize: "0.9em", color: "var(--fg-dim)", display: "flex", alignItems: "center", gap: "8px" }}>
                        <div className="spinner" style={{ width: "12px", height: "12px", border: "2px solid var(--fg-dim)", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }}></div>
                        {statusMessage}
                      </div>
                    )}
                  </div>
                  <div className="chat-input-area" style={{ padding: "20px", borderTop: "1px solid var(--border)" }}>
                    <div style={{ display: "flex", gap: "10px" }}>
                      <input 
                        type="text" 
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                        placeholder="Message Hydra..." 
                        style={{ flex: 1, padding: "10px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-dark)", color: "var(--fg)" }}
                      />
                      <button onClick={sendMessage} disabled={isLoading} style={{ padding: "10px 20px", borderRadius: "4px", backgroundColor: "var(--accent)", color: "white", border: "none", cursor: isLoading ? "not-allowed" : "pointer" }}>
                        Send
                      </button>
                    </div>
                  </div>
                  <style>{`
                    @keyframes spin { 100% { transform: rotate(360deg); } }
                  `}</style>
                </div>
              )}
              {activeEditorTab === "notes-1" && !selectedNote && (
                <div className="empty-state">
                  <FileText />
                  <h2>Notes</h2>
                  <p>Write your synthesis here. Select a note from the sidebar or click "+" to create a new one.</p>
                </div>
              )}
              {activeEditorTab === "notes-1" && selectedNote && (
                <div style={{ display: "flex", height: "100%", overflow: "hidden", width: "100%" }}>
                  {/* Editor side */}
                  <div style={{ flex: 1, borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", background: "var(--bg-dark)", height: "100%" }}>
                    <div style={{ padding: "12px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px" }}>
                      <input
                        type="text"
                        value={selectedNote.title}
                        onChange={(e) => setSelectedNote({ ...selectedNote, title: e.target.value })}
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
                          onClick={saveNote}
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
                          onClick={() => deleteNote(selectedNote.id)}
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
                    <textarea
                      value={selectedNote.body}
                      onChange={(e) => setSelectedNote({ ...selectedNote, body: e.target.value })}
                      style={{
                        flex: 1,
                        padding: "20px",
                        background: "var(--bg-dark)",
                        color: "var(--fg)",
                        border: "none",
                        resize: "none",
                        fontFamily: "inherit",
                        fontSize: "14px",
                        lineHeight: "1.6",
                        boxSizing: "border-box",
                        outline: "none"
                      }}
                      placeholder="Write your note content here... Use double brackets like [[Other Note Title]] to link notes."
                    />
                  </div>

                  {/* Obsidian sidebar / graph side */}
                  <div style={{ width: "320px", display: "flex", flexDirection: "column", background: "var(--bg)", overflowY: "auto", borderLeft: "1px solid var(--border)", height: "100%" }}>
                    <div style={{ padding: "12px", borderBottom: "1px solid var(--border)", fontWeight: "bold", fontSize: "12px", color: "var(--fg-dim)", letterSpacing: "0.5px" }}>
                      KNOWLEDGE GRAPH & LINKS
                    </div>

                    <div style={{ padding: "16px" }}>
                      <LocalGraphView
                        activeNode={{ id: selectedNote.id, title: selectedNote.title, type: "note" }}
                        neighbors={[
                          ...noteLinks.backlinks.map(l => ({ ...l, type: l.type || "note" })),
                          ...noteLinks.forward.map(l => ({ ...l, type: l.type || "note" }))
                        ].filter((v, i, a) => a.findIndex(t => t.id === v.id) === i)}
                        onNodeClick={(nodeId) => {
                          const found = notes.find(n => n.id === nodeId);
                          if (found) {
                            selectNote(found);
                          } else {
                            fetch(`http://localhost:8000/api/notes/${nodeId}`)
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
                                    fetch(`http://localhost:8000/api/notes/${link.id}`)
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
                                    fetch(`http://localhost:8000/api/notes/${link.id}`)
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
              )}
              {activeEditorTab === "writing-1" && (
                <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
                  <div style={{ padding: "12px", borderBottom: "1px solid var(--border)", display: "flex", gap: "8px" }}>
                    <button onClick={analyzeText} disabled={isReviewing} style={{ padding: "6px 12px", background: "var(--accent)", color: "white", borderRadius: "4px", border: "none", cursor: "pointer" }}>
                      {isReviewing ? "Analyzing..." : "Review Draft"}
                    </button>
                    {reviewData && (
                      <span style={{ fontSize: "13px", alignSelf: "center", color: "var(--fg-dim)" }}>
                        Issues: {reviewData.categories?.join(", ")}
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
                    <div style={{ flex: 1, borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column" }}>
                      <div style={{ padding: "8px", background: "var(--bg)", borderBottom: "1px solid var(--border)", fontSize: "12px", color: "var(--fg-dim)", fontWeight: "bold" }}>LATEX EDITOR</div>
                      <textarea 
                        value={draftText} 
                        onChange={(e) => setDraftText(e.target.value)} 
                        style={{ flex: 1, padding: "16px", background: "var(--bg-dark)", color: "var(--fg)", border: "none", resize: "none", fontFamily: "monospace" }} 
                        placeholder="Write your draft here..."
                      />
                    </div>
                    {reviewData ? (
                      <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "var(--bg)" }}>
                        <div style={{ padding: "8px", background: "var(--bg)", borderBottom: "1px solid var(--border)", fontSize: "12px", color: "var(--fg-dim)", fontWeight: "bold" }}>REVIEW SUGGESTIONS</div>
                        <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
                          {reviewData.critique?.map((c: string, i: number) => (
                            <div key={i} style={{ padding: "12px", marginBottom: "12px", background: "var(--bg-lighter)", borderRadius: "6px", borderLeft: "4px solid var(--accent)" }}>
                              <p style={{ margin: "0 0 8px 0", fontSize: "13px" }}>{c}</p>
                            </div>
                          ))}
                          {reviewData.unsupported_claims?.length > 0 && (
                            <div style={{ marginTop: "16px", padding: "12px", background: "rgba(239, 68, 68, 0.1)", borderRadius: "6px", borderLeft: "4px solid #ef4444" }}>
                              <h4 style={{ margin: "0 0 8px 0", fontSize: "13px", color: "#ef4444" }}>Unsupported Claims (Needs Evidence)</h4>
                              <ul style={{ margin: 0, paddingLeft: "20px", fontSize: "13px" }}>
                                {reviewData.unsupported_claims.map((claim: string, i: number) => (
                                  <li key={i}>{claim} <span style={{ color: "var(--accent)", cursor: "pointer", textDecoration: "underline" }} onClick={() => setActiveActivity("evidence")}>Link Evidence</span></li>
                                ))}
                              </ul>
                            </div>
                          )}
                          <div style={{ marginTop: "16px", padding: "12px", background: "var(--bg-lighter)", borderRadius: "6px" }}>
                            <h4 style={{ margin: "0 0 8px 0", fontSize: "13px" }}>Suggested Revision</h4>
                            <p style={{ fontSize: "13px", color: "var(--fg-dim)", whiteSpace: "pre-wrap" }}>{reviewData.rewrite}</p>
                            <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
                              <button onClick={() => { setDraftText(reviewData.rewrite); setReviewData(null); }} style={{ padding: "6px 12px", background: "var(--accent)", color: "white", borderRadius: "4px", border: "none", cursor: "pointer" }}>Accept Revision</button>
                              <button onClick={() => setReviewData(null)} style={{ padding: "6px 12px", background: "transparent", color: "var(--fg)", border: "1px solid var(--border)", borderRadius: "4px", cursor: "pointer" }}>Reject</button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "var(--bg)" }}>
                        <div style={{ padding: "8px", background: "var(--bg)", borderBottom: "1px solid var(--border)", fontSize: "12px", color: "var(--fg-dim)", fontWeight: "bold" }}>PDF PREVIEW</div>
                        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--fg-dim)" }}>
                          [PDF Preview Placeholder]
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Bottom Panel */}
        {bottomPanelOpen && (
          <div className="bottom-panel">
            <div className="panel-tabs">
              <div className="panel-tab active">Terminal</div>
              <div className="panel-tab">Output</div>
              <div className="panel-tab">Problems</div>
              <div style={{ flex: 1 }} />
              <div className="panel-tab" style={{ border: "none" }} onClick={() => setBottomPanelOpen(false)}>
                <X size={14} style={{ marginTop: 2 }} />
              </div>
            </div>
            <div className="panel-content">
              <div>hydra-web@0.1.0 dev</div>
              <div style={{ color: "var(--accent)", marginTop: 4 }}>➜  Local:   http://127.0.0.1:5173/</div>
              <div style={{ marginTop: 4 }}>➜  Network: use --host to expose</div>
              <div style={{ marginTop: 4 }}>ready in 245ms.</div>
            </div>
          </div>
        )}
      </main>

      {/* Status Bar */}
      <footer className="status-bar">
        <div className="status-group">
          <div className="status-item" onClick={() => setBottomPanelOpen(!bottomPanelOpen)}>
            <Terminal size={12} />
          </div>
          <div className="status-item">
            <CheckCircle2 size={12} />
            0 Errors
          </div>
        </div>
        <div className="status-group">
          <div className="status-item">
            <Activity size={12} />
            Phase 1
          </div>
        </div>
      </footer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
