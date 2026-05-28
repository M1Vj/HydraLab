import React from "react";
import { createRoot } from "react-dom/client";
import { Sparkles, FileText, BookOpenCheck, ListTodo, X, SplitSquareHorizontal } from "lucide-react";

import "./styles.css";

// Core context and registry
import { AppContextProvider, useAppContext } from "./core/context";
import { registry } from "./core/registry";

// Layout components
import { ActivityBar } from "./components/layout/ActivityBar";
import { SidebarFrame } from "./components/layout/SidebarFrame";
import { StatusBar } from "./components/layout/StatusBar";
import { TerminalPanel } from "./components/layout/TerminalPanel";

// Import modules to register them
import "./components/modules/ChatModule";
import "./components/modules/SourcesModule";
import "./components/modules/NotesModule";
import "./components/modules/EvidenceModule";
import "./components/modules/SettingsModule";
import "./components/modules/KanbanModule";
import "./components/modules/WritingModule";

// Global modals
import { KanbanTaskModal } from "./components/modules/KanbanModule";
import { ExportPreviewModal } from "./components/modules/SettingsModule";

function MainWorkspace() {
  const {
    sidebarOpen,
    activeEditorTab,
    setActiveEditorTab
  } = useAppContext();

  return (
    <div className={`workbench ${!sidebarOpen ? "sidebar-closed" : "sidebar-open"}`}>
      
      {/* Activity Bar */}
      <ActivityBar />

      {/* Sidebar */}
      <SidebarFrame />

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
              {activeEditorTab === "research-1" && registry.render("hydra.chat.main")}
              {activeEditorTab === "notes-1" && registry.render("hydra.notes.main")}
              {activeEditorTab === "writing-1" && registry.render("hydra.writing.main")}
              {activeEditorTab === "tasks-1" && registry.render("hydra.tasks.main")}
            </div>
          </div>
        </div>

        {/* Bottom Panel */}
        <TerminalPanel />
      </main>

      {/* Status Bar */}
      <StatusBar />

      {/* Global Modals */}
      <KanbanTaskModal />
      <ExportPreviewModal />
    </div>
  );
}

function App() {
  return (
    <AppContextProvider>
      <MainWorkspace />
    </AppContextProvider>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
