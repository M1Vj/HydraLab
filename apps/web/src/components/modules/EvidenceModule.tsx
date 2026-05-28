import React from "react";
import { useAppContext } from "../../core/context";
import { registry } from "../../core/registry";

export function EvidenceSidebar() {
  const { evidenceList } = useAppContext();

  return (
    <div style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "12px" }}>
      {evidenceList.length === 0 ? (
        <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
          <p>No evidence links found.</p>
        </div>
      ) : (
        evidenceList.map(ev => (
          <div 
            key={ev.id} 
            style={{ 
              padding: "12px", 
              backgroundColor: "var(--bg-dark)", 
              borderRadius: "6px",
              borderLeft: ev.support === "unsupported" 
                ? "4px solid #ef4444" 
                : ev.support === "weak" 
                  ? "4px solid #f59e0b" 
                  : "4px solid #10b981"
            }}
          >
            <div style={{ fontSize: "13px", fontWeight: "bold", marginBottom: "4px", color: "var(--fg)" }}>{ev.claim_text}</div>
            <div style={{ fontSize: "12px", color: "var(--fg-dim)", marginBottom: "8px", fontStyle: "italic" }}>"{ev.passage}"</div>
            <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between", color: "var(--fg-dim)" }}>
              <span>Source: {ev.source_title}</span>
              <span style={{ 
                color: ev.support === "unsupported" 
                  ? "#ef4444" 
                  : ev.support === "weak" 
                    ? "#f59e0b" 
                    : "#10b981"
              }}>
                {ev.support.toUpperCase()}
              </span>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

// Register components
registry.register("hydra.evidence", EvidenceSidebar);
