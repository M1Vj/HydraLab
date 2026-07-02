import { useMemo, useState } from "react";
import type React from "react";
import { BotMessageSquare, ChevronLeft, FileText, Highlighter, Inbox, ListTodo, ScrollText } from "lucide-react";
import type { CapabilityFlow, Surface } from "../../lib/responsive";
import { panelChrome, type PanelComponentProps, type PanelConfig, type PanelId } from "../../workspace/panelRegistry";
import type { ActiveProject } from "../../workspace/store";
import { MobileNav, type NavItem } from "./MobileNav";
import { UnsupportedSurfaceState } from "./UnsupportedSurfaceState";
import { ChatView, NotesView, ReadAnnotateView, ReviewView, TasksView } from "./views";

/**
 * Stack-based mobile root — the small-screen analogue of `WorkbenchShell`, but with a
 * simple navigation stack instead of the FlexLayout dock. It NEVER touches the desktop
 * layout store. It implements `openPanel` / `closeActivePanel` / `announce` shaped
 * exactly like `PanelComponentProps` so the reused desktop panels drop straight in.
 */

type PrimaryFlow = "read" | "review" | "annotate" | "notes" | "tasks" | "chat";

type FlowDefinition = {
  label: string;
  panelId: PanelId;
  render: (props: PanelComponentProps) => React.ReactElement;
};

const FLOWS: Record<PrimaryFlow, FlowDefinition> = {
  read: { label: "Read", panelId: "pdf-reader", render: (props) => <ReadAnnotateView {...props} /> },
  annotate: { label: "Annotate", panelId: "pdf-reader", render: (props) => <ReadAnnotateView {...props} /> },
  review: { label: "Review", panelId: "review-inbox", render: (props) => <ReviewView {...props} /> },
  notes: { label: "Notes", panelId: "markdown-editor", render: (props) => <NotesView {...props} /> },
  tasks: { label: "Tasks", panelId: "tasks", render: (props) => <TasksView {...props} /> },
  chat: { label: "Chat", panelId: "research-chat", render: (props) => <ChatView {...props} /> },
};

const NAV_ITEMS: readonly NavItem[] = [
  { flow: "read", label: "Read", icon: ScrollText },
  { flow: "review", label: "Review", icon: Inbox },
  { flow: "annotate", label: "Annotate", icon: Highlighter },
  { flow: "notes", label: "Notes", icon: FileText },
  { flow: "tasks", label: "Tasks", icon: ListTodo },
  { flow: "chat", label: "Chat", icon: BotMessageSquare },
];

/** Maps a desktop PanelId (from a reused panel's cross-navigation) to a mobile flow. */
const PANEL_TO_FLOW: Partial<Record<PanelId, PrimaryFlow>> = {
  "pdf-reader": "read",
  "review-inbox": "review",
  "markdown-editor": "notes",
  tasks: "tasks",
  "research-chat": "chat",
};

type StackEntry =
  | { kind: "flow"; flow: PrimaryFlow; panelId: PanelId; config: PanelConfig }
  | { kind: "unsupported"; title: string; reason: string };

function flowRoot(flow: PrimaryFlow): StackEntry {
  return { kind: "flow", flow, panelId: FLOWS[flow].panelId, config: {} };
}

export function MobileShell({ project, surface }: { project: ActiveProject; surface: Surface }) {
  const [stack, setStack] = useState<StackEntry[]>(() => [flowRoot("read")]);
  const [activeTab, setActiveTab] = useState<CapabilityFlow>("read");
  const [announcement, setAnnouncement] = useState("Mobile workspace ready");

  const active = stack[stack.length - 1];

  function announce(message: string) {
    setAnnouncement(message);
  }

  function openPanel(id: PanelId, config: PanelConfig = {}) {
    const flow = PANEL_TO_FLOW[id];
    if (!flow) {
      const title = panelChrome[id]?.title ?? id;
      setStack((current) => [
        ...current,
        { kind: "unsupported", title, reason: `${title} needs the multi-pane desktop workbench and is not offered as a mobile flow.` },
      ]);
      announce(`${title} is not available on this surface`);
      return;
    }
    setStack((current) => [...current, { kind: "flow", flow, panelId: id, config }]);
    setActiveTab(flow);
    announce(`Opened ${panelChrome[id]?.title ?? flow}`);
  }

  function closeActivePanel() {
    setStack((current) => (current.length > 1 ? current.slice(0, -1) : current));
  }

  function selectTab(flow: CapabilityFlow) {
    const primary = flow as PrimaryFlow;
    if (!FLOWS[primary]) return;
    setStack([flowRoot(primary)]);
    setActiveTab(primary);
    announce(`${FLOWS[primary].label} tab`);
  }

  const panelProps: (entry: Extract<StackEntry, { kind: "flow" }>) => PanelComponentProps = useMemo(
    () => (entry) => ({ panelId: entry.panelId, config: entry.config, openPanel, closeActivePanel, announce }),
    [],
  );

  return (
    <div className={`mobile-shell mobile-shell-${surface}`} data-surface={surface}>
      <div className="sr-only" aria-live="polite">
        {announcement}
      </div>
      <header className="mobile-topbar">
        {stack.length > 1 ? (
          <button type="button" className="mobile-back" onClick={closeActivePanel} aria-label="Back">
            <ChevronLeft size={18} aria-hidden />
          </button>
        ) : (
          <span className="mobile-brand" aria-hidden>
            HydraLab
          </span>
        )}
        <span className="mobile-project-name" title={project.path}>
          {project.name}
        </span>
      </header>

      <main className="mobile-stage">
        {active.kind === "unsupported" ? (
          <UnsupportedSurfaceState title={active.title} reason={active.reason} />
        ) : (
          FLOWS[active.flow].render(panelProps(active))
        )}
      </main>

      <MobileNav items={NAV_ITEMS} active={activeTab} onSelect={selectTab} surface={surface} />
    </div>
  );
}
