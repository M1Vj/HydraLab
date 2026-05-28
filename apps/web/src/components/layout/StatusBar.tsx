import React from "react";
import { Terminal, CheckCircle2, Activity } from "lucide-react";
import { useAppContext } from "../../core/context";

export function StatusBar() {
  const { bottomPanelOpen, setBottomPanelOpen } = useAppContext();

  return (
    <footer className="status-bar">
      <div className="status-group">
        <div 
          className="status-item" 
          onClick={() => setBottomPanelOpen(!bottomPanelOpen)}
          style={{ cursor: "pointer" }}
        >
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
  );
}
