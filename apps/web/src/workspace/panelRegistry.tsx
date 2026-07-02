import type React from "react";
import type { IJsonModel, IJsonTabNode } from "flexlayout-react";
import {
  BookOpenCheck,
  BotMessageSquare,
  Bug,
  FileSearch,
  FileText,
  FolderTree,
  GitBranch,
  Globe2,
  Inbox,
  ListTodo,
  PenLine,
  ScrollText,
  Settings,
  Terminal,
} from "lucide-react";

export type PanelId =
  | "explorer"
  | "source-discovery"
  | "review-inbox"
  | "git"
  | "research-chat"
  | "markdown-editor"
  | "pdf-reader"
  | "browser"
  | "writing"
  | "citation-evidence"
  | "tasks"
  | "settings"
  | "logs"
  | "problems";

export type PanelLocation = "border-left" | "border-bottom" | "center" | "border-right";
export type PanelConfig = Record<string, unknown>;
export type PanelComponentProps = {
  panelId: PanelId;
  config?: PanelConfig;
  openPanel: (id: PanelId, config?: PanelConfig) => void;
  closeActivePanel: () => void;
  announce: (message: string) => void;
};

export type PanelDefinition = {
  id: PanelId;
  title: string;
  icon: React.ComponentType<{ size?: number; "aria-hidden"?: boolean }>;
  defaultLocation: PanelLocation;
  singleton: boolean;
  allowMultiple: boolean;
  component: React.ComponentType<PanelComponentProps>;
};

export type PanelRegistry = Record<PanelId, PanelDefinition>;

export type RegisterPanelInput = Omit<PanelDefinition, "component"> & {
  component?: React.ComponentType<PanelComponentProps>;
};

export const panelChrome: Record<PanelId, Omit<PanelDefinition, "component">> = {
  explorer: { id: "explorer", title: "Explorer", icon: FolderTree, defaultLocation: "border-left", singleton: true, allowMultiple: false },
  "source-discovery": {
    id: "source-discovery",
    title: "Source Discovery",
    icon: FileSearch,
    defaultLocation: "border-left",
    singleton: true,
    allowMultiple: false,
  },
  "review-inbox": { id: "review-inbox", title: "Review Inbox", icon: Inbox, defaultLocation: "border-left", singleton: true, allowMultiple: false },
  git: { id: "git", title: "Git", icon: GitBranch, defaultLocation: "border-left", singleton: true, allowMultiple: false },
  "research-chat": { id: "research-chat", title: "Research Chat", icon: BotMessageSquare, defaultLocation: "center", singleton: true, allowMultiple: false },
  "markdown-editor": { id: "markdown-editor", title: "Markdown Editor", icon: FileText, defaultLocation: "center", singleton: false, allowMultiple: true },
  "pdf-reader": { id: "pdf-reader", title: "PDF Reader", icon: ScrollText, defaultLocation: "center", singleton: false, allowMultiple: true },
  browser: { id: "browser", title: "Browser", icon: Globe2, defaultLocation: "center", singleton: false, allowMultiple: true },
  writing: { id: "writing", title: "Writing & Formats", icon: PenLine, defaultLocation: "center", singleton: true, allowMultiple: false },
  "citation-evidence": {
    id: "citation-evidence",
    title: "Citation & Evidence",
    icon: BookOpenCheck,
    defaultLocation: "border-right",
    singleton: true,
    allowMultiple: false,
  },
  tasks: { id: "tasks", title: "Tasks", icon: ListTodo, defaultLocation: "border-right", singleton: true, allowMultiple: false },
  settings: { id: "settings", title: "Settings", icon: Settings, defaultLocation: "border-right", singleton: true, allowMultiple: false },
  logs: { id: "logs", title: "Logs", icon: Terminal, defaultLocation: "border-bottom", singleton: true, allowMultiple: false },
  problems: { id: "problems", title: "Problems", icon: Bug, defaultLocation: "border-bottom", singleton: true, allowMultiple: false },
};

export const panelIds = Object.keys(panelChrome) as PanelId[];

export function createPanelRegistry(components: Partial<Record<PanelId, React.ComponentType<PanelComponentProps>>>): PanelRegistry {
  const missing: React.ComponentType<PanelComponentProps> = ({ panelId }) => (
    <div className="panel-state not-wired" role="status">
      <strong>{panelChrome[panelId].title}</strong>
      <span>This panel is registered but not wired yet.</span>
    </div>
  );
  return Object.fromEntries(panelIds.map((id) => [id, { ...panelChrome[id], component: components[id] ?? missing }])) as PanelRegistry;
}

export function defaultWorkbenchLayout(): IJsonModel {
  return {
    global: {
      enableEdgeDock: true,
      tabEnableRename: false,
      tabEnableClose: true,
      tabEnableDrag: true,
      tabSetEnableMaximize: true,
      tabSetEnableDrop: true,
    },
    borders: [
      {
        type: "border",
        location: "left",
        size: 292,
        selected: 0,
        children: [
          tab("explorer"),
          tab("source-discovery"),
          tab("review-inbox"),
          tab("git"),
        ],
      },
      {
        type: "border",
        location: "bottom",
        size: 180,
        selected: 0,
        children: [tab("logs"), tab("problems")],
      },
    ],
    layout: {
      type: "row",
      id: "root",
      weight: 100,
      children: [
        {
          type: "tabset",
          id: "center_main",
          weight: 76,
          selected: 0,
          enableMaximize: true,
          children: [tab("research-chat"), tab("markdown-editor"), tab("writing"), tab("pdf-reader"), tab("browser")],
        },
        {
          type: "tabset",
          id: "right_main",
          weight: 24,
          selected: 0,
          enableMaximize: true,
          children: [tab("citation-evidence"), tab("tasks"), tab("settings")],
        },
      ],
    },
  };
}

export function tab(panelId: PanelId, config: PanelConfig = {}): IJsonTabNode {
  const stable = tabStableKey(panelId, config);
  return {
    type: "tab",
    id: stable,
    name: panelTitle(panelId, config),
    component: panelId,
    config,
    enableClose: true,
    enableDrag: true,
  };
}

export function panelTitle(panelId: PanelId, config: PanelConfig = {}): string {
  if (panelId === "markdown-editor" && typeof config.title === "string") return config.title;
  if (panelId === "pdf-reader" && typeof config.title === "string") return config.title;
  if (panelId === "browser" && typeof config.url === "string") return new URL(config.url).hostname;
  return panelChrome[panelId].title;
}

export function tabStableKey(panelId: PanelId, config: PanelConfig = {}): string {
  const identity =
    panelId === "markdown-editor"
      ? config.noteId ?? config.fileRef ?? "default"
      : panelId === "pdf-reader"
        ? config.sourceId ?? "local"
        : panelId === "browser"
          ? config.url ?? "default"
          : "singleton";
  return `${panelId}:${String(identity)}`;
}
