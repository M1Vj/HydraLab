import React from "react";
import { useAppContext } from "../../core/context";
import { registry } from "../../core/registry";

export function SidebarFrame() {
  const { activeActivity, sidebarOpen } = useAppContext();

  if (!sidebarOpen) return null;

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span>{activeActivity.toUpperCase()}</span>
      </div>
      <div className="sidebar-content">
        {registry.render(`hydra.${activeActivity}`)}
      </div>
    </aside>
  );
}
