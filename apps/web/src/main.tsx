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
  SplitSquareHorizontal,
  Plus,
  Trash2,
  Edit3,
  ExternalLink,
  Clock
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

  // Kanban Tasks State
  const [tasks, setTasks] = useState<any[]>([]);
  const [sources, setSources] = useState<any[]>([]);
  const [isTaskModalOpen, setIsTaskModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<any | null>(null);
  const [selectedTask, setSelectedTask] = useState<any | null>(null);
  const [draggedTaskId, setDraggedTaskId] = useState<string | null>(null);
  const [draggedOverColumn, setDraggedOverColumn] = useState<string | null>(null);
  const [taskModalColumn, setTaskModalColumn] = useState("to_do");

  // Settings States
  const [openaiModel, setOpenaiModel] = useState("gpt-4o");
  const [openaiApiKey, setOpenaiApiKey] = useState("");
  const [anthropicModel, setAnthropicModel] = useState("claude-3-5-sonnet");
  const [anthropicApiKey, setAnthropicApiKey] = useState("");
  const [geminiModel, setGeminiModel] = useState("gemini-1.5-pro");
  const [geminiApiKey, setGeminiApiKey] = useState("");
  const [themePreference, setThemePreference] = useState("dark");
  const [defaultProvider, setDefaultProvider] = useState("openai");
  const [systemInstruction, setSystemInstruction] = useState("You are an expert research partner. Analyze sources rigorously.");
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [settingsStatus, setSettingsStatus] = useState("");

  // Export States
  const [isPreviewModalOpen, setIsPreviewModalOpen] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);
  const [isExportLoading, setIsExportLoading] = useState(false);

  const fetchTasks = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/tasks");
      const data = await res.json();
      setTasks(data.tasks || []);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchSources = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/export/workspace");
      const data = await res.json();
      setSources(data.sources || []);
    } catch (err) {
      console.error(err);
    }
  };

  const handleCreateOrUpdateTask = async (taskData: { title: string; detail: string; column: string; progress: number; phase_indicator: string; position: number }) => {
    try {
      if (editingTask?.id) {
        const res = await fetch(`http://localhost:8000/api/tasks/${editingTask.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(taskData)
        });
        if (res.ok) {
          fetchTasks();
          setIsTaskModalOpen(false);
          setEditingTask(null);
        }
      } else {
        const res = await fetch("http://localhost:8000/api/tasks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(taskData)
        });
        if (res.ok) {
          fetchTasks();
          setIsTaskModalOpen(false);
          setEditingTask(null);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    if (!confirm("Are you sure you want to delete this task?")) return;
    try {
      const res = await fetch(`http://localhost:8000/api/tasks/${taskId}`, {
        method: "DELETE"
      });
      if (res.ok) {
        fetchTasks();
        if (selectedTask?.id === taskId) {
          setSelectedTask(null);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const moveTask = async (taskId: string, targetColumn: string) => {
    const taskToMove = tasks.find(t => t.id === taskId);
    if (!taskToMove) return;
    if (taskToMove.column === targetColumn) return;

    // Calculate position
    const columnTasks = tasks.filter(t => t.column === targetColumn);
    const position = columnTasks.length;

    try {
      // Optimistic update
      setTasks(prev => prev.map(t => t.id === taskId ? { ...t, column: targetColumn, position } : t));

      await fetch(`http://localhost:8000/api/tasks/${taskId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ column: targetColumn, position })
      });
      fetchTasks();
    } catch (err) {
      console.error(err);
      fetchTasks();
    }
  };

  const handleDragStart = (e: React.DragEvent, taskId: string) => {
    e.dataTransfer.setData("text/plain", taskId);
    setDraggedTaskId(taskId);
  };

  const handleDragOver = (e: React.DragEvent, column: string) => {
    e.preventDefault();
    setDraggedOverColumn(column);
  };

  const handleDragLeave = () => {
    setDraggedOverColumn(null);
  };

  const handleDrop = (e: React.DragEvent, targetColumn: string) => {
    e.preventDefault();
    const taskId = e.dataTransfer.getData("text/plain") || draggedTaskId;
    if (taskId) {
      moveTask(taskId, targetColumn);
    }
    setDraggedTaskId(null);
    setDraggedOverColumn(null);
  };

  const getLinkedContext = (detailText: string) => {
    const wikiPattern = /\[\[([^\]|]+)(?:\|[^\]]*)?\]\]/g;
    const links: string[] = [];
    let match;
    while ((match = wikiPattern.exec(detailText || "")) !== null) {
      links.push(match[1].trim());
    }

    const linkedNotes = notes.filter(n => 
      links.some(l => l.toLowerCase() === n.title.toLowerCase() || l === n.id)
    );

    const linkedSourcesList = sources.filter(s => 
      links.some(l => l.toLowerCase() === s.title.toLowerCase() || l === s.id)
    );

    return { linkedNotes, linkedSources: linkedSourcesList };
  };

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

  const fetchSettings = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/settings");
      const data = await res.json();
      if (data.provider_settings) {
        data.provider_settings.forEach((p: any) => {
          if (p.provider === "openai") {
            setOpenaiModel(p.model);
            setOpenaiApiKey(p.api_key_ref);
          } else if (p.provider === "anthropic") {
            setAnthropicModel(p.model);
            setAnthropicApiKey(p.api_key_ref);
          } else if (p.provider === "gemini") {
            setGeminiModel(p.model);
            setGeminiApiKey(p.api_key_ref);
          }
        });
      }
      if (data.workspace_preferences) {
        if (data.workspace_preferences.theme) setThemePreference(data.workspace_preferences.theme);
        if (data.workspace_preferences.default_provider) setDefaultProvider(data.workspace_preferences.default_provider);
        if (data.workspace_preferences.system_instruction) setSystemInstruction(data.workspace_preferences.system_instruction);
      }
    } catch (err) {
      console.error("Failed to load settings:", err);
    }
  };

  const handleSaveSettings = async () => {
    setIsSavingSettings(true);
    setSettingsStatus("");
    try {
      const payload = {
        provider_settings: [
          { provider: "openai", model: openaiModel, api_key_ref: openaiApiKey },
          { provider: "anthropic", model: anthropicModel, api_key_ref: anthropicApiKey },
          { provider: "gemini", model: geminiModel, api_key_ref: geminiApiKey }
        ],
        workspace_preferences: {
          theme: themePreference,
          default_provider: defaultProvider,
          system_instruction: systemInstruction
        }
      };
      const res = await fetch("http://localhost:8000/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        setSettingsStatus("Settings saved successfully!");
        setTimeout(() => setSettingsStatus(""), 3000);
      } else {
        setSettingsStatus("Error saving settings.");
      }
    } catch (err) {
      console.error(err);
      setSettingsStatus("Failed to save settings.");
    } finally {
      setIsSavingSettings(false);
    }
  };

  const handleExportPreview = async () => {
    setIsExportLoading(true);
    try {
      const res = await fetch("http://localhost:8000/api/export/preview");
      const data = await res.json();
      setPreviewData(data);
      setIsPreviewModalOpen(true);
    } catch (err) {
      console.error(err);
      alert("Failed to load export preview.");
    } finally {
      setIsExportLoading(false);
    }
  };

  const handleTriggerExport = async () => {
    try {
      const response = await fetch("http://localhost:8000/api/export", {
        method: "POST"
      });
      if (!response.ok) throw new Error("Export failed");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "hydra_export.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      setIsPreviewModalOpen(false);
    } catch (err) {
      console.error(err);
      alert("Failed to export workspace.");
    }
  };

  React.useEffect(() => {
    fetchTasks();
    fetchSources();
    fetchSettings();
  }, []);

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
            <div style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "12px", height: "100%", boxSizing: "border-box" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <button
                  onClick={() => {
                    setActiveEditorTab("tasks-1");
                  }}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    background: "var(--bg-active)",
                    color: "var(--text-active)",
                    borderRadius: "4px",
                    border: "1px solid var(--border-color)",
                    cursor: "pointer",
                    fontSize: "12px",
                    fontWeight: "bold",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px"
                  }}
                >
                  <ExternalLink size={13} />
                  Open Full Kanban Board
                </button>
                <button
                  onClick={() => {
                    setEditingTask(null);
                    setTaskModalColumn("to_do");
                    setIsTaskModalOpen(true);
                  }}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    background: "var(--accent)",
                    color: "white",
                    borderRadius: "4px",
                    border: "none",
                    cursor: "pointer",
                    fontSize: "12px",
                    fontWeight: "bold",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px"
                  }}
                >
                  <Plus size={13} />
                  New Task
                </button>
              </div>

              <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "8px" }}>
                {tasks.length === 0 ? (
                  <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
                    <p style={{ color: "var(--text-muted)", fontSize: "12px" }}>No tasks found.</p>
                  </div>
                ) : (
                  tasks.map(t => {
                    const colNames: Record<string, string> = {
                      to_do: "To Do",
                      in_progress: "In Progress",
                      review: "Review",
                      done: "Done"
                    };
                    const colColors: Record<string, string> = {
                      to_do: "#969696",
                      in_progress: "#007acc",
                      review: "#8b5cf6",
                      done: "#10b981"
                    };
                    return (
                      <div
                        key={t.id}
                        onClick={() => setSelectedTask(t)}
                        style={{
                          padding: "10px",
                          backgroundColor: selectedTask?.id === t.id ? "var(--bg-active)" : "var(--bg-base)",
                          borderRadius: "6px",
                          border: selectedTask?.id === t.id ? "1px solid var(--accent)" : "1px solid var(--border-color)",
                          cursor: "pointer",
                          transition: "all 0.15s"
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "4px" }}>
                          <span style={{ fontWeight: "600", fontSize: "12.5px", color: "var(--text-active)" }}>{t.title}</span>
                          <span style={{
                            fontSize: "9px",
                            padding: "2px 5px",
                            borderRadius: "3px",
                            backgroundColor: `${colColors[t.column || "to_do"]}20`,
                            color: colColors[t.column || "to_do"],
                            border: `1px solid ${colColors[t.column || "to_do"]}40`,
                            fontWeight: "bold",
                            whiteSpace: "nowrap"
                          }}>
                            {colNames[t.column || "to_do"]}
                          </span>
                        </div>
                        {t.detail && (
                          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {t.detail}
                          </div>
                        )}
                        {t.progress > 0 && (
                          <div className="kanban-progress-container" style={{ marginTop: "6px" }}>
                            <div className="kanban-progress-bar-bg" style={{ height: "3px" }}>
                              <div className="kanban-progress-bar-fill" style={{ width: `${t.progress}%` }} />
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
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
          {activeActivity === "settings" && (
            <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "16px", height: "100%", overflowY: "auto", boxSizing: "border-box" }}>
              <div>
                <h3 style={{ fontSize: "14px", fontWeight: "bold", margin: "0 0 12px 0", color: "var(--fg)" }}>Model Providers</h3>
                
                {/* OpenAI */}
                <div style={{ marginBottom: "12px", padding: "10px", borderRadius: "6px", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border)" }}>
                  <div style={{ fontSize: "12px", fontWeight: "bold", color: "#10b981", marginBottom: "8px" }}>OpenAI</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <input 
                      type="text" 
                      placeholder="Model (e.g. gpt-4o)" 
                      value={openaiModel} 
                      onChange={(e) => setOpenaiModel(e.target.value)}
                      style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)" }}
                    />
                    <input 
                      type="password" 
                      placeholder="API Key or env reference" 
                      value={openaiApiKey} 
                      onChange={(e) => setOpenaiApiKey(e.target.value)}
                      style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)" }}
                    />
                  </div>
                </div>

                {/* Anthropic */}
                <div style={{ marginBottom: "12px", padding: "10px", borderRadius: "6px", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border)" }}>
                  <div style={{ fontSize: "12px", fontWeight: "bold", color: "#d97706", marginBottom: "8px" }}>Anthropic</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <input 
                      type="text" 
                      placeholder="Model (e.g. claude-3-5-sonnet)" 
                      value={anthropicModel} 
                      onChange={(e) => setAnthropicModel(e.target.value)}
                      style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)" }}
                    />
                    <input 
                      type="password" 
                      placeholder="API Key or env reference" 
                      value={anthropicApiKey} 
                      onChange={(e) => setAnthropicApiKey(e.target.value)}
                      style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)" }}
                    />
                  </div>
                </div>

                {/* Gemini */}
                <div style={{ marginBottom: "12px", padding: "10px", borderRadius: "6px", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border)" }}>
                  <div style={{ fontSize: "12px", fontWeight: "bold", color: "#8b5cf6", marginBottom: "8px" }}>Gemini</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <input 
                      type="text" 
                      placeholder="Model (e.g. gemini-1.5-pro)" 
                      value={geminiModel} 
                      onChange={(e) => setGeminiModel(e.target.value)}
                      style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)" }}
                    />
                    <input 
                      type="password" 
                      placeholder="API Key or env reference" 
                      value={geminiApiKey} 
                      onChange={(e) => setGeminiApiKey(e.target.value)}
                      style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)" }}
                    />
                  </div>
                </div>
              </div>

              <div>
                <h3 style={{ fontSize: "14px", fontWeight: "bold", margin: "0 0 12px 0", color: "var(--fg)" }}>Workspace Preferences</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: "10px", padding: "10px", borderRadius: "6px", backgroundColor: "var(--bg-dark)", border: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    <label style={{ fontSize: "11px", color: "var(--fg-dim)", fontWeight: "500" }}>Default Provider</label>
                    <select 
                      value={defaultProvider} 
                      onChange={(e) => setDefaultProvider(e.target.value)}
                      style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)", outline: "none" }}
                    >
                      <option value="openai">OpenAI</option>
                      <option value="anthropic">Anthropic</option>
                      <option value="gemini">Gemini</option>
                    </select>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    <label style={{ fontSize: "11px", color: "var(--fg-dim)", fontWeight: "500" }}>Theme</label>
                    <select 
                      value={themePreference} 
                      onChange={(e) => setThemePreference(e.target.value)}
                      style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)", outline: "none" }}
                    >
                      <option value="light">Light</option>
                      <option value="dark">Dark</option>
                      <option value="glassmorphism">Glassmorphism</option>
                    </select>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                    <label style={{ fontSize: "11px", color: "var(--fg-dim)", fontWeight: "500" }}>System Instructions</label>
                    <textarea 
                      rows={3}
                      value={systemInstruction} 
                      onChange={(e) => setSystemInstruction(e.target.value)}
                      placeholder="Enter system prompt instructions..."
                      style={{ padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)", backgroundColor: "var(--bg-base)", color: "var(--fg)", resize: "vertical" }}
                    />
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <button 
                  onClick={handleSaveSettings}
                  disabled={isSavingSettings}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    backgroundColor: "var(--accent)",
                    color: "white",
                    border: "none",
                    borderRadius: "4px",
                    cursor: "pointer",
                    fontWeight: "600",
                    fontSize: "13px",
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center"
                  }}
                >
                  {isSavingSettings ? "Saving Settings..." : "Save Configuration"}
                </button>
                {settingsStatus && (
                  <div style={{ fontSize: "12px", textAlign: "center", color: settingsStatus.includes("successfully") ? "#10b981" : "#ef4444" }}>
                    {settingsStatus}
                  </div>
                )}
              </div>

              <div style={{ borderTop: "1px solid var(--border)", paddingTop: "16px", marginTop: "8px" }}>
                <h3 style={{ fontSize: "14px", fontWeight: "bold", margin: "0 0 8px 0", color: "var(--fg)" }}>Data Export</h3>
                <p style={{ fontSize: "11px", color: "var(--fg-dim)", margin: "0 0 12px 0", lineHeight: "1.4" }}>
                  Export your notes, citations, Kanban tasks, and sources into a local workspace ZIP bundle.
                </p>
                <button 
                  onClick={handleExportPreview}
                  disabled={isExportLoading}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    backgroundColor: "var(--bg-dark)",
                    color: "var(--fg)",
                    border: "1px solid var(--border)",
                    borderRadius: "4px",
                    cursor: "pointer",
                    fontWeight: "600",
                    fontSize: "13px",
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                    gap: "8px"
                  }}
                >
                  {isExportLoading ? "Preparing Preview..." : "Export Workspace (ZIP)"}
                </button>
              </div>
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
            <div 
              className={`editor-tab ${activeEditorTab === "tasks-1" ? "active" : ""}`}
              onClick={() => setActiveEditorTab("tasks-1")}
            >
              <ListTodo size={14} />
              Kanban Board
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
              {activeEditorTab === "tasks-1" && (
                <div style={{ display: "flex", height: "100%", width: "100%", overflow: "hidden" }}>
                  <div style={{ flex: 1, display: "flex", flexDirection: "column", height: "100%", minWidth: 0 }}>
                    {/* Board Header Actions */}
                    <div style={{ padding: "12px 20px", borderBottom: "1px solid var(--border-color)", display: "flex", justifyContent: "space-between", alignItems: "center", backgroundColor: "var(--bg-sidebar)" }}>
                      <span style={{ fontSize: "14px", fontWeight: "bold", color: "var(--text-active)", display: "flex", alignItems: "center", gap: "8px" }}>
                        <ListTodo size={16} />
                        Research Workbench Kanban
                      </span>
                      <button
                        onClick={() => {
                          setEditingTask(null);
                          setTaskModalColumn("to_do");
                          setIsTaskModalOpen(true);
                        }}
                        style={{
                          padding: "6px 12px",
                          background: "var(--accent)",
                          color: "white",
                          borderRadius: "4px",
                          border: "none",
                          cursor: "pointer",
                          fontSize: "12.5px",
                          fontWeight: "bold",
                          display: "flex",
                          alignItems: "center",
                          gap: "6px"
                        }}
                      >
                        <Plus size={14} />
                        Create Task
                      </button>
                    </div>

                    {/* Columns Wrapper */}
                    <div className="kanban-board" style={{ flex: 1, display: "flex", gap: "16px", padding: "16px", overflowX: "auto" }}>
                      {(["to_do", "in_progress", "review", "done"] as const).map(col => {
                        const colNames: Record<string, string> = {
                          to_do: "To Do",
                          in_progress: "In Progress",
                          review: "Review",
                          done: "Done"
                        };
                        const colColors: Record<string, string> = {
                          to_do: "#969696",
                          in_progress: "#007acc",
                          review: "#8b5cf6",
                          done: "#10b981"
                        };
                        const columnTasks = tasks
                          .filter(t => (t.column || "to_do") === col)
                          .sort((a, b) => (a.position || 0) - (b.position || 0));

                        return (
                          <div
                            key={col}
                            className={`kanban-column ${draggedOverColumn === col ? "drag-over" : ""}`}
                            onDragOver={(e) => handleDragOver(e, col)}
                            onDragLeave={handleDragLeave}
                            onDrop={(e) => handleDrop(e, col)}
                          >
                            <div className="kanban-column-header">
                              <span className="kanban-column-title">
                                <span style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: colColors[col], display: "inline-block" }} />
                                {colNames[col]}
                              </span>
                              <span className="kanban-card-count">{columnTasks.length}</span>
                            </div>

                            <div className="kanban-cards-list">
                              {columnTasks.map(t => {
                                const { linkedNotes, linkedSources } = getLinkedContext(t.detail);
                                return (
                                  <div
                                    key={t.id}
                                    className="kanban-card"
                                    draggable
                                    onDragStart={(e) => handleDragStart(e, t.id)}
                                    onClick={() => setSelectedTask(t)}
                                    style={{
                                      borderLeft: `4px solid ${colColors[col]}`,
                                      backgroundColor: selectedTask?.id === t.id ? "var(--bg-active)" : "var(--bg-base)"
                                    }}
                                  >
                                    <div className="kanban-card-title">{t.title}</div>
                                    {t.detail && <div className="kanban-card-detail">{t.detail}</div>}

                                    {t.phase_indicator && (
                                      <div className="kanban-phase-badge">
                                        <Clock size={10} style={{ marginRight: "4px", verticalAlign: "middle" }} />
                                        {t.phase_indicator}
                                      </div>
                                    )}

                                    {t.progress > 0 && (
                                      <div className="kanban-progress-container">
                                        <div className="kanban-progress-bar-bg">
                                          <div className="kanban-progress-bar-fill" style={{ width: `${t.progress}%` }} />
                                        </div>
                                        <div className="kanban-progress-text">
                                          <span>Progress</span>
                                          <span>{t.progress}%</span>
                                        </div>
                                      </div>
                                    )}

                                    {/* Wiki Links Badges */}
                                    {(linkedNotes.length > 0 || linkedSources.length > 0) && (
                                      <div className="kanban-card-links">
                                        {linkedNotes.map(n => (
                                          <span
                                            key={n.id}
                                            className="kanban-card-link-badge"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              selectNote(n);
                                            }}
                                          >
                                            <FileText size={10} />
                                            {n.title}
                                          </span>
                                        ))}
                                        {linkedSources.map(s => (
                                          <span
                                            key={s.id}
                                            className="kanban-card-link-badge"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              setActiveActivity("sources");
                                            }}
                                          >
                                            <Library size={10} />
                                            {s.title}
                                          </span>
                                        ))}
                                      </div>
                                    )}

                                    <div className="kanban-card-actions">
                                      <button
                                        className="kanban-card-action-btn"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          setEditingTask(t);
                                          setTaskModalColumn(t.column || "to_do");
                                          setIsTaskModalOpen(true);
                                        }}
                                        title="Edit Task"
                                      >
                                        <Edit3 size={12} />
                                      </button>
                                      <button
                                        className="kanban-card-action-btn"
                                        style={{ color: "#f43f5e" }}
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleDeleteTask(t.id);
                                        }}
                                        title="Delete Task"
                                      >
                                        <Trash2 size={12} />
                                      </button>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>

                            <button
                              className="kanban-add-card-btn"
                              onClick={() => {
                                setEditingTask(null);
                                setTaskModalColumn(col);
                                setIsTaskModalOpen(true);
                              }}
                            >
                              <Plus size={13} />
                              Add Task
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Linked Context Panel (Sidebar inside board) */}
                  {selectedTask && (
                    <div className="linked-context-panel">
                      <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border-color)", display: "flex", justifyContent: "space-between", alignItems: "center", backgroundColor: "rgba(255, 255, 255, 0.02)" }}>
                        <span style={{ fontSize: "11px", fontWeight: "bold", textTransform: "uppercase", color: "var(--text-muted)", letterSpacing: "0.5px" }}>Task Context</span>
                        <button
                          onClick={() => setSelectedTask(null)}
                          style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center" }}
                        >
                          <X size={14} />
                        </button>
                      </div>

                      <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "16px", overflowY: "auto", flex: 1 }}>
                        <div>
                          <h4 style={{ margin: "0 0 6px 0", fontSize: "14px", color: "var(--text-active)" }}>{selectedTask.title}</h4>
                          <div style={{ display: "flex", gap: "8px", alignItems: "center", marginTop: "8px" }}>
                            <span style={{
                              fontSize: "10px",
                              padding: "2px 6px",
                              borderRadius: "4px",
                              backgroundColor: "var(--bg-active)",
                              border: "1px solid var(--border-color)",
                              fontWeight: "bold",
                              textTransform: "uppercase"
                            }}>
                              Column: {selectedTask.column}
                            </span>
                            {selectedTask.progress > 0 && (
                              <span style={{ fontSize: "10px", color: "var(--text-muted)", fontWeight: "500" }}>
                                {selectedTask.progress}% Progress
                              </span>
                            )}
                          </div>
                        </div>

                        {selectedTask.detail && (
                          <div>
                            <div style={{ fontSize: "11px", fontWeight: "bold", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "6px", letterSpacing: "0.5px" }}>Description</div>
                            <div style={{ fontSize: "12.5px", color: "var(--text-main)", backgroundColor: "var(--bg-base)", border: "1px solid var(--border-color)", padding: "10px", borderRadius: "6px", whiteSpace: "pre-wrap", lineHeight: "1.45" }}>
                              {selectedTask.detail}
                            </div>
                          </div>
                        )}

                        {/* Linked Notes */}
                        {(() => {
                          const { linkedNotes, linkedSources } = getLinkedContext(selectedTask.detail);
                          return (
                            <>
                              <div>
                                <div style={{ fontSize: "11px", fontWeight: "bold", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "8px", letterSpacing: "0.5px" }}>Linked Notes ({linkedNotes.length})</div>
                                {linkedNotes.length === 0 ? (
                                  <div style={{ fontSize: "11.5px", color: "var(--text-muted)", fontStyle: "italic" }}>No linked notes. Use [[Note Title]] in description.</div>
                                ) : (
                                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                                    {linkedNotes.map(n => (
                                      <div
                                        key={n.id}
                                        onClick={() => selectNote(n)}
                                        style={{
                                          padding: "8px 10px",
                                          backgroundColor: "var(--bg-base)",
                                          border: "1px solid var(--border-color)",
                                          borderRadius: "4px",
                                          cursor: "pointer",
                                          fontSize: "12px",
                                          color: "var(--text-main)",
                                          transition: "all 0.15s"
                                        }}
                                      >
                                        <div style={{ fontWeight: "600", color: "var(--accent)" }}>{n.title}</div>
                                        <div style={{ fontSize: "10.5px", color: "var(--text-muted)", marginTop: "2px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{n.body}</div>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>

                              <div>
                                <div style={{ fontSize: "11px", fontWeight: "bold", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "8px", letterSpacing: "0.5px" }}>Linked Sources ({linkedSources.length})</div>
                                {linkedSources.length === 0 ? (
                                  <div style={{ fontSize: "11.5px", color: "var(--text-muted)", fontStyle: "italic" }}>No linked sources. Use [[Source Title]] in description.</div>
                                ) : (
                                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                                    {linkedSources.map(s => (
                                      <div
                                        key={s.id}
                                        onClick={() => setActiveActivity("sources")}
                                        style={{
                                          padding: "8px 10px",
                                          backgroundColor: "var(--bg-base)",
                                          border: "1px solid var(--border-color)",
                                          borderRadius: "4px",
                                          cursor: "pointer",
                                          fontSize: "12px",
                                          color: "var(--text-main)",
                                          transition: "all 0.15s"
                                        }}
                                      >
                                        <div style={{ fontWeight: "600", color: "#10b981" }}>{s.title}</div>
                                        {s.authors && <div style={{ fontSize: "10.5px", color: "var(--text-muted)", marginTop: "2px" }}>{s.authors}</div>}
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            </>
                          );
                        })()}
                      </div>
                    </div>
                  )}
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

      {/* Kanban Task Modal Overlay */}
      {isTaskModalOpen && (
        <div className="kanban-modal-overlay">
          <form
            className="kanban-modal"
            onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.currentTarget);
              handleCreateOrUpdateTask({
                title: formData.get("title") as string,
                detail: formData.get("detail") as string,
                column: formData.get("column") as string,
                progress: parseInt(formData.get("progress") as string || "0"),
                phase_indicator: formData.get("phase_indicator") as string || "",
                position: editingTask?.position || 0
              });
            }}
          >
            <h3 className="kanban-modal-title">
              {editingTask ? `Edit Task: ${editingTask.title}` : "Create New Task"}
            </h3>

            <div className="kanban-form-group">
              <label className="kanban-form-label">Task Title *</label>
              <input
                name="title"
                type="text"
                required
                defaultValue={editingTask?.title || ""}
                placeholder="Enter task title..."
                className="kanban-input"
              />
            </div>

            <div className="kanban-form-group">
              <label className="kanban-form-label">Description & Links (e.g. [[Note Title]])</label>
              <textarea
                name="detail"
                rows={4}
                defaultValue={editingTask?.detail || ""}
                placeholder="Describe task... Reference other notes using [[Note Title]]"
                className="kanban-textarea"
              />
            </div>

            <div style={{ display: "flex", gap: "12px" }}>
              <div className="kanban-form-group" style={{ flex: 1 }}>
                <label className="kanban-form-label">Column</label>
                <select
                  name="column"
                  defaultValue={editingTask?.column || taskModalColumn}
                  className="kanban-select"
                >
                  <option value="to_do">To Do</option>
                  <option value="in_progress">In Progress</option>
                  <option value="review">Review</option>
                  <option value="done">Done</option>
                </select>
              </div>

              <div className="kanban-form-group" style={{ flex: 1 }}>
                <label className="kanban-form-label">Progress (%)</label>
                <input
                  name="progress"
                  type="number"
                  min="0"
                  max="100"
                  defaultValue={editingTask?.progress || 0}
                  className="kanban-input"
                />
              </div>
            </div>

            <div className="kanban-form-group">
              <label className="kanban-form-label">Phase Indicator (optional)</label>
              <select
                name="phase_indicator"
                defaultValue={editingTask?.phase_indicator || ""}
                className="kanban-select"
              >
                <option value="">None</option>
                <option value="retrieving sources">Retrieving Sources</option>
                <option value="summarising papers">Summarising Papers</option>
                <option value="drafting report">Drafting Report</option>
              </select>
            </div>

            <div className="kanban-modal-actions">
              <button
                type="button"
                className="kanban-btn kanban-btn-secondary"
                onClick={() => {
                  setIsTaskModalOpen(false);
                  setEditingTask(null);
                }}
              >
                Cancel
              </button>
              <button type="submit" className="kanban-btn kanban-btn-primary">
                {editingTask ? "Save Changes" : "Create Task"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Export Preview Modal Overlay */}
      {isPreviewModalOpen && previewData && (
        <div className="kanban-modal-overlay">
          <div className="kanban-modal" style={{ maxWidth: "500px", width: "95%" }}>
            <h3 className="kanban-modal-title">Export Workspace Preview</h3>
            <p style={{ fontSize: "12px", color: "var(--fg-dim)", margin: "0 0 16px 0", lineHeight: "1.4" }}>
              Please review the files and counts that will be bundled into your zip archive.
            </p>

            <div style={{ backgroundColor: "var(--bg-dark)", border: "1px solid var(--border)", borderRadius: "6px", padding: "12px", display: "flex", flexWrap: "wrap", gap: "12px", marginBottom: "16px" }}>
              <div style={{ flex: "1 1 40%", display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: "11px", color: "var(--fg-dim)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Notes</span>
                <span style={{ fontSize: "20px", fontWeight: "bold", color: "var(--fg)" }}>{previewData.counts?.notes || 0}</span>
              </div>
              <div style={{ flex: "1 1 40%", display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: "11px", color: "var(--fg-dim)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Citations</span>
                <span style={{ fontSize: "20px", fontWeight: "bold", color: "var(--fg)" }}>{previewData.counts?.citations || 0}</span>
              </div>
              <div style={{ flex: "1 1 40%", display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: "11px", color: "var(--fg-dim)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Kanban Tasks</span>
                <span style={{ fontSize: "20px", fontWeight: "bold", color: "var(--fg)" }}>{previewData.counts?.tasks || 0}</span>
              </div>
              <div style={{ flex: "1 1 40%", display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: "11px", color: "var(--fg-dim)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Sources</span>
                <span style={{ fontSize: "20px", fontWeight: "bold", color: "var(--fg)" }}>{previewData.counts?.sources || 0}</span>
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginBottom: "20px" }}>
              <span style={{ fontSize: "12px", fontWeight: "600", color: "var(--fg)" }}>Archive File Structure:</span>
              <div style={{
                maxHeight: "150px",
                overflowY: "auto",
                backgroundColor: "var(--bg-dark)",
                border: "1px solid var(--border)",
                borderRadius: "6px",
                padding: "8px",
                fontFamily: "monospace",
                fontSize: "11px",
                color: "var(--fg-dim)"
              }}>
                {previewData.files && previewData.files.map((file: string) => (
                  <div key={file} style={{ display: "flex", alignItems: "center", gap: "6px", padding: "3px 0" }}>
                    <span style={{ color: "var(--accent)" }}>📁</span>
                    <span>{file}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="kanban-modal-actions">
              <button
                type="button"
                className="kanban-btn kanban-btn-secondary"
                onClick={() => setIsPreviewModalOpen(false)}
              >
                Cancel
              </button>
              <button 
                type="button" 
                className="kanban-btn kanban-btn-primary"
                onClick={handleTriggerExport}
              >
                Download ZIP
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
