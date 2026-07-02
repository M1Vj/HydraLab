import type { PanelId } from "./panelRegistry";
import type { NoteRecord, SourceRecord, TaskRecord, ClaimRecord, CitationRecord } from "../lib/api";

export type CommandId =
  | "workbench.palette"
  | "workbench.new-note"
  | "workbench.shortcuts"
  | "workbench.toggle-terminal"
  | "workbench.close-project"
  | "review.open"
  | "git.init"
  | "view.reset-layout"
  | "view.save-layout-as"
  | "view.switch-layout"
  | "workbench.close-active-tab"
  | "workbench.split-editor-tabset"
  | string;

export type CommandAction = {
  id: CommandId;
  title: string;
  group?: string;
  disabledReason?: string;
  run: () => void | Promise<void>;
};

export type QuickOpenObject = {
  objectId: string;
  type: "note" | "source" | "task" | "claim" | "citation";
  title: string;
  subtitle?: string;
};

export type PaletteResults = {
  actions: CommandAction[];
  panels: Array<{ panelId: PanelId; title: string }>;
  quickOpen: QuickOpenObject[];
};

export class CommandRegistry {
  private commands = new Map<string, CommandAction>();

  register(command: CommandAction) {
    this.commands.set(command.id, command);
  }

  registerMany(commands: CommandAction[]) {
    for (const command of commands) this.register(command);
  }

  get(id: string) {
    return this.commands.get(id);
  }

  all() {
    return [...this.commands.values()].sort((a, b) => a.title.localeCompare(b.title));
  }

  async run(id: string) {
    const command = this.commands.get(id);
    if (!command || command.disabledReason) return false;
    await command.run();
    return true;
  }
}

export function buildPaletteResults(input: {
  commands: CommandAction[];
  panels: Array<{ panelId: PanelId; title: string }>;
  quickOpen: QuickOpenObject[];
  query: string;
}): PaletteResults {
  const query = input.query.trim().toLowerCase();
  const matches = (text: string) => !query || text.toLowerCase().includes(query);
  return {
    actions: input.commands.filter((command) => matches(`${command.title} ${command.id}`)),
    panels: input.panels.filter((panel) => matches(`${panel.title} ${panel.panelId}`)),
    quickOpen: input.quickOpen.filter((object) => matches(`${object.title} ${object.subtitle ?? ""} ${object.type}`)),
  };
}

export function quickOpenFromObjects(objects: {
  notes: NoteRecord[];
  sources: SourceRecord[];
  tasks: TaskRecord[];
  claims: ClaimRecord[];
  citations: CitationRecord[];
}): QuickOpenObject[] {
  return [
    ...objects.notes.map((note) => ({ objectId: note.id, type: "note" as const, title: note.title, subtitle: note.relative_path })),
    ...objects.sources.map((source) => ({ objectId: source.id, type: "source" as const, title: source.title, subtitle: source.url })),
    ...objects.tasks.map((task) => ({ objectId: task.id, type: "task" as const, title: task.title, subtitle: task.column })),
    ...objects.claims.map((claim) => ({ objectId: claim.id, type: "claim" as const, title: claim.text, subtitle: claim.status })),
    ...objects.citations.map((citation) => ({
      objectId: citation.id,
      type: "citation" as const,
      title: citation.text,
      subtitle: citation.citation_key || citation.source_id,
    })),
  ];
}
