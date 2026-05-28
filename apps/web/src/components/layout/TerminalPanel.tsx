import React from "react";
import { X } from "lucide-react";
import { useAppContext } from "../../core/context";

export function TerminalPanel() {
  const { bottomPanelOpen, setBottomPanelOpen } = useAppContext();

  if (!bottomPanelOpen) return null;

  return (
    <div className="bottom-panel">
      <div className="panel-tabs">
        <div className="panel-tab active">Terminal</div>
        <div className="panel-tab">Output</div>
        <div className="panel-tab">Problems</div>
        <div style={{ flex: 1 }} />
        <div 
          className="panel-tab" 
          style={{ border: "none", cursor: "pointer" }} 
          onClick={() => setBottomPanelOpen(false)}
        >
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
  );
}
