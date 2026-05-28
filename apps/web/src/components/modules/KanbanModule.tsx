import React from "react";
import { ExternalLink, Plus, Clock, FileText, Library, Edit3, Trash2, ListTodo, X } from "lucide-react";
import { useAppContext, Task } from "../../core/context";
import { registry } from "../../core/registry";

export function TasksSidebar() {
  const {
    tasks,
    selectedTask,
    setSelectedTask,
    setActiveEditorTab,
    setEditingTask,
    setTaskModalColumn,
    setIsTaskModalOpen
  } = useAppContext();

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
          tasks.map(t => (
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
          ))
        )}
      </div>
    </div>
  );
}

export function TasksMain() {
  const {
    tasks,
    selectedTask,
    setSelectedTask,
    draggedOverColumn,
    setEditingTask,
    setTaskModalColumn,
    setIsTaskModalOpen,
    handleDragStart,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    getLinkedContext,
    handleDeleteTask,
    selectNote,
    setActiveActivity
  } = useAppContext();

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

            {/* Linked Notes & Sources */}
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
  );
}

// Register components
registry.register("hydra.tasks", TasksSidebar);
registry.register("hydra.tasks.main", TasksMain);

export function KanbanTaskModal() {
  const {
    isTaskModalOpen,
    setIsTaskModalOpen,
    editingTask,
    setEditingTask,
    taskModalColumn,
    handleCreateOrUpdateTask
  } = useAppContext();

  if (!isTaskModalOpen) return null;

  return (
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
  );
}

