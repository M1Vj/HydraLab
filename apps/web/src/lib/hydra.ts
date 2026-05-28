export type Source = {
  id?: string;
  title: string;
  authors?: string;
  year?: string;
  url?: string;
  abstract?: string;
};

export type Task = {
  id: string;
  title: string;
  detail?: string;
  column: string;
  progress: number;
};

export type KanbanColumn = {
  name: string;
  tasks: Task[];
};

export const KANBAN_COLUMNS = ["To Do", "In Progress", "Review", "Done"] as const;

export function sourceLabel(source: Source): string {
  const author = source.authors?.trim() || "Unknown author";
  const year = source.year?.trim() || "n.d.";
  return `${source.title} - ${author} (${year})`;
}

export function groupTasksByColumn(tasks: Task[]): KanbanColumn[] {
  return KANBAN_COLUMNS.map((name) => ({
    name,
    tasks: tasks.filter((task) => task.column === name),
  }));
}

export function statusCopy(status: string): string {
  if (status === "completed") {
    return "Cited answer ready";
  }
  if (status === "error") {
    return "Needs review";
  }
  return "Working";
}

export async function apiJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`Hydra API error ${response.status}`);
  }
  return response.json() as Promise<T>;
}
