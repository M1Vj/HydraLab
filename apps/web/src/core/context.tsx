import React, { createContext, useContext, useState, useEffect } from "react";

export type ActivityType = "chat" | "sources" | "notes" | "tasks" | "settings" | "evidence";

export interface Message {
  id: string;
  role: string;
  content: string;
}

export interface Task {
  id: string;
  title: string;
  detail: string;
  column: string;
  progress: number;
  phase_indicator?: string;
  position: number;
}

export interface Source {
  id: string;
  title: string;
  authors?: string;
  [key: string]: any;
}

export interface Note {
  id: string;
  title: string;
  body: string;
  source_id?: string | null;
  relative_path?: string;
  trust_origin?: "user" | "assistant" | "untrusted";
}

export interface NoteLinks {
  backlinks: any[];
  forward: any[];
}

export interface Evidence {
  id: string;
  claim_text: string;
  passage: string;
  source_title: string;
  support: "unsupported" | "weak" | "supported" | string;
}

export interface AppContextType {
  activeActivity: ActivityType;
  setActiveActivity: React.Dispatch<React.SetStateAction<ActivityType>>;
  sidebarOpen: boolean;
  setSidebarOpen: React.Dispatch<React.SetStateAction<boolean>>;
  bottomPanelOpen: boolean;
  setBottomPanelOpen: React.Dispatch<React.SetStateAction<boolean>>;
  activeEditorTab: string;
  setActiveEditorTab: React.Dispatch<React.SetStateAction<string>>;
  draftText: string;
  setDraftText: React.Dispatch<React.SetStateAction<string>>;
  reviewData: any;
  setReviewData: React.Dispatch<React.SetStateAction<any>>;
  isReviewing: boolean;
  messages: Message[];
  inputValue: string;
  setInputValue: React.Dispatch<React.SetStateAction<string>>;
  isLoading: boolean;
  statusMessage: string;
  conversationId: string | null;
  evidenceList: Evidence[];

  // Kanban Tasks
  tasks: Task[];
  sources: Source[];
  isTaskModalOpen: boolean;
  setIsTaskModalOpen: React.Dispatch<React.SetStateAction<boolean>>;
  editingTask: Task | null;
  setEditingTask: React.Dispatch<React.SetStateAction<Task | null>>;
  selectedTask: Task | null;
  setSelectedTask: React.Dispatch<React.SetStateAction<Task | null>>;
  draggedTaskId: string | null;
  setDraggedTaskId: React.Dispatch<React.SetStateAction<string | null>>;
  draggedOverColumn: string | null;
  setDraggedOverColumn: React.Dispatch<React.SetStateAction<string | null>>;
  taskModalColumn: string;
  setTaskModalColumn: React.Dispatch<React.SetStateAction<string>>;

  // Settings
  openaiModel: string;
  setOpenaiModel: React.Dispatch<React.SetStateAction<string>>;
  openaiApiKey: string;
  setOpenaiApiKey: React.Dispatch<React.SetStateAction<string>>;
  anthropicModel: string;
  setAnthropicModel: React.Dispatch<React.SetStateAction<string>>;
  anthropicApiKey: string;
  setAnthropicApiKey: React.Dispatch<React.SetStateAction<string>>;
  geminiModel: string;
  setGeminiModel: React.Dispatch<React.SetStateAction<string>>;
  geminiApiKey: string;
  setGeminiApiKey: React.Dispatch<React.SetStateAction<string>>;
  themePreference: string;
  setThemePreference: React.Dispatch<React.SetStateAction<string>>;
  defaultProvider: string;
  setDefaultProvider: React.Dispatch<React.SetStateAction<string>>;
  systemInstruction: string;
  setSystemInstruction: React.Dispatch<React.SetStateAction<string>>;
  isSavingSettings: boolean;
  settingsStatus: string;

  // Export
  isPreviewModalOpen: boolean;
  setIsPreviewModalOpen: React.Dispatch<React.SetStateAction<boolean>>;
  previewData: any;
  isExportLoading: boolean;

  // Notes
  notes: Note[];
  notesQuery: string;
  setNotesQuery: React.Dispatch<React.SetStateAction<string>>;
  selectedNote: Note | null;
  setSelectedNote: React.Dispatch<React.SetStateAction<Note | null>>;
  noteLinks: NoteLinks;
  setNoteLinks: React.Dispatch<React.SetStateAction<NoteLinks>>;

  // Functions
  fetchTasks: () => Promise<void>;
  fetchSources: () => Promise<void>;
  handleCreateOrUpdateTask: (taskData: { title: string; detail: string; column: string; progress: number; phase_indicator: string; position: number }) => Promise<void>;
  handleDeleteTask: (taskId: string) => Promise<void>;
  moveTask: (taskId: string, targetColumn: string) => Promise<void>;
  handleDragStart: (e: React.DragEvent, taskId: string) => void;
  handleDragOver: (e: React.DragEvent, column: string) => void;
  handleDragLeave: () => void;
  handleDrop: (e: React.DragEvent, targetColumn: string) => void;
  getLinkedContext: (detailText: string) => { linkedNotes: Note[]; linkedSources: Source[] };
  fetchNotes: (q?: string) => Promise<void>;
  fetchNoteLinks: (noteId: string) => Promise<void>;
  selectNote: (note: Note) => void;
  createNewNote: () => Promise<void>;
  saveNote: () => Promise<void>;
  deleteNote: (noteId: string) => Promise<void>;
  fetchSettings: () => Promise<void>;
  handleSaveSettings: () => Promise<void>;
  handleExportPreview: () => Promise<void>;
  handleTriggerExport: () => Promise<void>;
  analyzeText: () => Promise<void>;
  sendMessage: () => Promise<void>;
  toggleSidebar: (activity: ActivityType) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppContextProvider({ children }: { children: React.ReactNode }) {
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
  const [evidenceList, setEvidenceList] = useState<Evidence[]>([]);

  // Kanban Tasks State
  const [tasks, setTasks] = useState<Task[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [isTaskModalOpen, setIsTaskModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
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

  // Notes States
  const [notes, setNotes] = useState<Note[]>([]);
  const [notesQuery, setNotesQuery] = useState("");
  const [selectedNote, setSelectedNote] = useState<Note | null>(null);
  const [noteLinks, setNoteLinks] = useState<NoteLinks>({ backlinks: [], forward: [] });

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

  const selectNote = (note: Note) => {
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
      const res = await fetch("/api/settings");
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
      const res = await fetch("/api/settings", {
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

  useEffect(() => {
    fetchTasks();
    fetchSources();
    fetchSettings();
  }, []);

  useEffect(() => {
    fetchNotes(notesQuery);
  }, [notesQuery]);

  useEffect(() => {
    if (activeActivity === "evidence") {
      fetch("http://localhost:8000/api/evidence")
        .then(r => r.json())
        .then(data => setEvidenceList(data.evidence || []))
        .catch(console.error);
    }
  }, [activeActivity]);

  return (
    <AppContext.Provider
      value={{
        activeActivity,
        setActiveActivity,
        sidebarOpen,
        setSidebarOpen,
        bottomPanelOpen,
        setBottomPanelOpen,
        activeEditorTab,
        setActiveEditorTab,
        draftText,
        setDraftText,
        reviewData,
        setReviewData,
        isReviewing,
        messages,
        inputValue,
        setInputValue,
        isLoading,
        statusMessage,
        conversationId,
        evidenceList,

        // Kanban Tasks
        tasks,
        sources,
        isTaskModalOpen,
        setIsTaskModalOpen,
        editingTask,
        setEditingTask,
        selectedTask,
        setSelectedTask,
        draggedTaskId,
        setDraggedTaskId,
        draggedOverColumn,
        setDraggedOverColumn,
        taskModalColumn,
        setTaskModalColumn,

        // Settings
        openaiModel,
        setOpenaiModel,
        openaiApiKey,
        setOpenaiApiKey,
        anthropicModel,
        setAnthropicModel,
        anthropicApiKey,
        setAnthropicApiKey,
        geminiModel,
        setGeminiModel,
        geminiApiKey,
        setGeminiApiKey,
        themePreference,
        setThemePreference,
        defaultProvider,
        setDefaultProvider,
        systemInstruction,
        setSystemInstruction,
        isSavingSettings,
        settingsStatus,

        // Export
        isPreviewModalOpen,
        setIsPreviewModalOpen,
        previewData,
        isExportLoading,

        // Notes
        notes,
        notesQuery,
        setNotesQuery,
        selectedNote,
        setSelectedNote,
        noteLinks,
        setNoteLinks,

        // Functions
        fetchTasks,
        fetchSources,
        handleCreateOrUpdateTask,
        handleDeleteTask,
        moveTask,
        handleDragStart,
        handleDragOver,
        handleDragLeave,
        handleDrop,
        getLinkedContext,
        fetchNotes,
        fetchNoteLinks,
        selectNote,
        createNewNote,
        saveNote,
        deleteNote,
        fetchSettings,
        handleSaveSettings,
        handleExportPreview,
        handleTriggerExport,
        analyzeText,
        sendMessage,
        toggleSidebar
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error("useAppContext must be used within an AppContextProvider");
  }
  return context;
}
