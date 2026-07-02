import { useEffect, useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { api, type TaskRecord } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { EmptyState, FailureState, LoadingState, PanelScaffold } from "./PanelState";
import { useWorkspaceData } from "../data";

const columns = ["to_do", "in_progress", "review", "done"];

export function TasksPanel({ announce }: PanelComponentProps) {
  const { objects } = useWorkspaceData();
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    void loadTasks();
  }, []);

  async function loadTasks() {
    setLoading(true);
    setError(null);
    try {
      const payload = await api.get<{ tasks: TaskRecord[] }>("/api/tasks");
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

  const byColumn = useMemo(
    () =>
      tasks.reduce<Record<string, TaskRecord[]>>((groups, task) => {
        const key = task.column || "to_do";
        groups[key] = [...(groups[key] ?? []), task];
        return groups;
      }, {}),
    [tasks],
  );

  if (loading) return <LoadingState title="Loading tasks" />;
  if (error) return <FailureState error={error} onRetry={loadTasks} />;

  return (
    <PanelScaffold title="Tasks">
      <header className="panel-toolbar">
        <button onClick={() => void createTask()}>
          <Plus size={14} /> Add task
        </button>
      </header>
      {tasks.length === 0 ? (
        <EmptyState title="Empty board" message="Research-linked tasks will appear here." action="Add task" onAction={() => void createTask()} />
      ) : (
        <div className="kanban-board">
          {columns.map((column) => (
            <section key={column} className="kanban-column">
              <h3>{column.replaceAll("_", " ")}</h3>
              {(byColumn[column] ?? []).map((task) => (
                <article key={task.id} className="task-card" draggable onDragStart={(event) => event.dataTransfer.setData("task/id", task.id)}>
                  <strong>{task.title}</strong>
                  {task.detail && <p>{task.detail}</p>}
                  <select value={task.column} onChange={(event) => void moveTask(task, event.target.value)} aria-label={`Move ${task.title}`}>
                    {columns.map((choice) => (
                      <option key={choice} value={choice}>
                        {choice}
                      </option>
                    ))}
                  </select>
                </article>
              ))}
              <div
                className="drop-zone"
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  const task = tasks.find((item) => item.id === event.dataTransfer.getData("task/id"));
                  if (task) void moveTask(task, column);
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
