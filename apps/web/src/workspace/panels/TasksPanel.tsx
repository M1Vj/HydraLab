import { useEffect, useMemo, useState } from "react";
import { Check, Plus, X } from "lucide-react";
import { api, type TaskRecord } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";
import { useWorkspaceData } from "../data";
import { KANBAN_COLUMNS, activeTasks, collectTags, draftTasks, filterByTag, groupByColumn } from "./tasksController";

export function TasksPanel({ announce }: PanelComponentProps) {
  const { objects, review } = useWorkspaceData();
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [tagFilter, setTagFilter] = useState<string | null>(null);

  useEffect(() => {
    void loadTasks();
  }, []);

  async function loadTasks() {
    setLoading(true);
    setError(null);
    try {
      const payload = await api.get<{ tasks: TaskRecord[] }>("/api/tasks?state=all");
      setTasks(payload.tasks);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    } finally {
      setLoading(false);
    }
  }

  async function createTask() {
    const created = await api.post<TaskRecord>("/api/tasks", { title: "Untitled task", column: "to_do" });
    setTasks((current) => [...current, created]);
    objects.reload();
  }

  async function moveTask(task: TaskRecord, column: string) {
    const previous = tasks;
    setTasks(moveTaskOptimistically(tasks, task.id, column));
    try {
      const updated = await api.patch<TaskRecord>(`/api/tasks/${encodeURIComponent(task.id)}`, { column });
      setTasks((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      announce(`Moved task to ${column}`);
    } catch (caught) {
      setTasks(previous);
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  async function acceptDraft(task: TaskRecord) {
    const updated = await api.post<TaskRecord>(`/api/tasks/${encodeURIComponent(task.id)}/accept`);
    setTasks((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    announce(`Accepted task ${task.title}`);
    review.reload();
  }

  async function dismissDraft(task: TaskRecord) {
    const updated = await api.post<TaskRecord>(`/api/tasks/${encodeURIComponent(task.id)}/dismiss`);
    setTasks((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    announce(`Dismissed task ${task.title}`);
    review.reload();
  }

  const active = useMemo(() => filterByTag(activeTasks(tasks), tagFilter), [tasks, tagFilter]);
  const drafts = useMemo(() => filterByTag(draftTasks(tasks), tagFilter), [tasks, tagFilter]);
  const byColumn = useMemo(() => groupByColumn(active), [active]);
  const tags = useMemo(() => collectTags(tasks), [tasks]);

  if (loading) return <LoadingState title="Loading tasks" />;
  if (error) return <FailureState error={error} onRetry={loadTasks} />;

  return (
    <PanelScaffold title="Tasks">
      <header className="panel-toolbar">
        <button onClick={() => void createTask()}>
          <Plus size={14} /> Add task
        </button>
        <label className="tag-filter">
          <span className="sr-only">Filter by tag</span>
          <select value={tagFilter ?? ""} onChange={(event) => setTagFilter(event.target.value || null)} aria-label="Filter by tag">
            <option value="">All tags</option>
            {tags.map((tag) => (
              <option key={tag} value={tag}>
                {tag}
              </option>
            ))}
          </select>
        </label>
      </header>

      {drafts.length > 0 && (
        <section className="task-drafts" aria-label="Suggested tasks">
          <h3>Suggested ({drafts.length})</h3>
          {drafts.map((task) => (
            <article key={task.id} className="task-card draft" aria-label={`Suggested task ${task.title}`}>
              <span className="origin-badge">{task.origin === "auto" ? "auto-draft" : "assistant"}</span>
              <strong>{task.title}</strong>
              {task.review_category && <small className="review-flag">needs review: {task.review_category}</small>}
              <div className="task-badge-actions">
                <button onClick={() => void acceptDraft(task)} aria-label={`Accept ${task.title}`}>
                  <Check size={13} /> Accept
                </button>
                <button onClick={() => void dismissDraft(task)} aria-label={`Dismiss ${task.title}`}>
                  <X size={13} /> Dismiss
                </button>
              </div>
            </article>
          ))}
        </section>
      )}

      {active.length === 0 && drafts.length === 0 ? (
        <EmptyState title="Empty board" message="Research-linked tasks will appear here." action="Add task" onAction={() => void createTask()} />
      ) : (
        <div className="kanban-board">
          {KANBAN_COLUMNS.map((column) => (
            <section key={column.id} className="kanban-column">
              <h3>{column.label}</h3>
              {(byColumn[column.id] ?? []).map((task) => (
                <article key={task.id} className="task-card" draggable onDragStart={(event) => event.dataTransfer.setData("task/id", task.id)}>
                  <strong>{task.title}</strong>
                  {task.detail && <p>{task.detail}</p>}
                  <div className="task-meta">
                    {task.priority && task.priority !== "normal" && <span className={`priority ${task.priority}`}>{task.priority}</span>}
                    {task.due && <span className="due">due {task.due}</span>}
                    {(task.tags ?? []).map((tag) => (
                      <span key={tag} className="tag-chip">
                        {tag}
                      </span>
                    ))}
                  </div>
                  <select value={task.column} onChange={(event) => void moveTask(task, event.target.value)} aria-label={`Move ${task.title}`}>
                    {KANBAN_COLUMNS.map((choice) => (
                      <option key={choice.id} value={choice.id}>
                        {choice.label}
                      </option>
                    ))}
                  </select>
                </article>
              ))}
              <div
                className="drop-zone"
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  const task = active.find((item) => item.id === event.dataTransfer.getData("task/id"));
                  if (task) void moveTask(task, column.id);
                }}
              />
            </section>
          ))}
        </div>
      )}
    </PanelScaffold>
  );
}

export function moveTaskOptimistically(tasks: TaskRecord[], taskId: string, column: string): TaskRecord[] {
  return tasks.map((task) => (task.id === taskId ? { ...task, column } : task));
}
