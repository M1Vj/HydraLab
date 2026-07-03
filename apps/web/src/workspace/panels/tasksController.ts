import type { TaskRecord } from "../../lib/api";

/** The four normative Kanban columns (HL-UX-01): id maps to task.status/column. */
export const KANBAN_COLUMNS: Array<{ id: string; label: string }> = [
  { id: "to_do", label: "To Do" },
  { id: "in_progress", label: "In Progress" },
  { id: "review", label: "Review" },
  { id: "done", label: "Done" },
];

export const COLUMN_IDS = KANBAN_COLUMNS.map((column) => column.id);

/** Only active tasks appear on the board columns (drafts render as badges). */
export function activeTasks(tasks: TaskRecord[]): TaskRecord[] {
  return tasks.filter((task) => (task.lifecycle_state ?? "active") === "active");
}

export function draftTasks(tasks: TaskRecord[]): TaskRecord[] {
  return tasks.filter((task) => task.lifecycle_state === "draft");
}

/** HL-UX-02: filtering the board by a tag hides non-matching tasks. */
export function filterByTag(tasks: TaskRecord[], tag: string | null): TaskRecord[] {
  if (!tag) return tasks;
  return tasks.filter((task) => (task.tags ?? []).includes(tag));
}

export function collectTags(tasks: TaskRecord[]): string[] {
  const set = new Set<string>();
  for (const task of tasks) for (const tag of task.tags ?? []) set.add(tag);
  return [...set].sort();
}

export function groupByColumn(tasks: TaskRecord[]): Record<string, TaskRecord[]> {
  return tasks.reduce<Record<string, TaskRecord[]>>((groups, task) => {
    const key = task.column || "to_do";
    groups[key] = [...(groups[key] ?? []), task];
    return groups;
  }, {});
}
