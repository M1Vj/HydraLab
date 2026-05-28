import React from "react";
import { MessageSquareText, Library, FileText, ListTodo, ShieldCheck, Settings } from "lucide-react";
import { useAppContext } from "../../core/context";

export function ActivityBar() {
  const { activeActivity, toggleSidebar } = useAppContext();

  return (
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
  );
}
