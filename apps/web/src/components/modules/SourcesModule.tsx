import React from "react";
import { useAppContext } from "../../core/context";
import { registry } from "../../core/registry";

export function SourcesSidebar() {
  const { sources } = useAppContext();

  if (sources.length === 0) {
    return (
      <div className="empty-state" style={{ height: "auto", marginTop: "40px" }}>
        <p>No sources uploaded.</p>
      </div>
    );
  }

  return (
    <div style={{ padding: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
      {sources.map(s => (
        <div 
          key={s.id} 
          style={{ 
            padding: "10px", 
            backgroundColor: "var(--bg-dark)", 
            borderRadius: "6px", 
            border: "1px solid var(--border)" 
          }}
        >
          <div style={{ fontWeight: "bold", fontSize: "13px", color: "var(--fg)" }}>{s.title}</div>
          {s.authors && <div style={{ fontSize: "11px", color: "var(--fg-dim)", marginTop: "4px" }}>{s.authors}</div>}
        </div>
      ))}
    </div>
  );
}

// Register components
registry.register("hydra.sources", SourcesSidebar);
