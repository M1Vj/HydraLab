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
  Sparkles,
  Terminal,
  Activity,
  X,
  SplitSquareHorizontal
} from "lucide-react";

import "./styles.css";

type ActivityType = "chat" | "sources" | "notes" | "tasks" | "settings";

function App() {
  const [activeActivity, setActiveActivity] = useState<ActivityType>("chat");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [bottomPanelOpen, setBottomPanelOpen] = useState(true);
  const [activeEditorTab, setActiveEditorTab] = useState("research-1");

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
            <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
              <p>No notes available.</p>
            </div>
          )}
          {activeActivity === "tasks" && (
            <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
              <p>No active tasks.</p>
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
            <div style={{ flex: 1 }} />
            <div className="editor-tab" style={{ border: "none", cursor: "default" }}>
              <SplitSquareHorizontal size={14} style={{ cursor: "pointer", opacity: 0.7 }} />
            </div>
          </div>

          <div className="editor-pane-container">
            <div className="editor-pane">
              {activeEditorTab === "research-1" && (
                <div className="empty-state">
                  <Sparkles />
                  <h2>Hydra Research</h2>
                  <p>Ask a question, upload a paper, or synthesize your notes. I will generate citations and trace claims back to their source.</p>
                  <button>New Research Chat</button>
                </div>
              )}
              {activeEditorTab === "notes-1" && (
                <div className="empty-state">
                  <FileText />
                  <h2>Notes</h2>
                  <p>Write your synthesis here. Your sources and evidence review will guide your drafting.</p>
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
