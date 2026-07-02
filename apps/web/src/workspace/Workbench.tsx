import { useEffect, useMemo, useRef, useState } from "react";
import { Layout, Model, type IJsonModel, type ILayoutApi, type TabNode } from "flexlayout-react";
import "flexlayout-react/style/dark.css";
import { CheckCircle2, FolderOpen, PanelBottom, Plus, RotateCcw, Save, X } from "lucide-react";
import { api } from "../lib/api";
import { CommandPalette, ShortcutReference } from "./CommandPalette";
import { CommandRegistry } from "./commands";
import { WorkspaceDataProvider, useWorkspaceData } from "./data";
import { activeJsonLayout, openPanelInLayout, removeActiveTabFromLayout } from "./layout";
import { createPanelRegistry, panelChrome, panelIds, type PanelComponentProps, type PanelId } from "./panelRegistry";
import { useWorkspaceStore, type ActiveProject, type RecentProject } from "./store";
import { ExplorerPanel } from "./panels/ExplorerPanel";
import { SourceDiscoveryPanel } from "./panels/SourceDiscoveryPanel";
import { ResearchChatPanel } from "./panels/ResearchChatPanel";
import { MarkdownEditorPanel } from "./panels/MarkdownEditorPanel";
import { WritingPanel } from "./panels/WritingPanel";
import { TasksPanel } from "./panels/TasksPanel";
import { BrowserPanel } from "./panels/BrowserPanel";
import {
  CitationEvidencePanel,
  ExportPanel,
  GitPanel,
  LogsPanel,
  PdfReaderPanel,
  ProblemsPanel,
  ReviewInboxPanel,
  SettingsPanel,
  TerminalPanel,
} from "./panels/ResearchObjectPanels";

export function WorkbenchRoot() {
  const activeProject = useWorkspaceStore((state) => state.activeProject);
  return activeProject ? (
    <WorkspaceDataProvider projectId={activeProject.id}>
      <WorkbenchShell project={activeProject} />
    </WorkspaceDataProvider>
  ) : (
    <WelcomeSurface />
  );
}

function WorkbenchShell({ project }: { project: ActiveProject }) {
  const store = useWorkspaceStore();
  const data = useWorkspaceData();
  const layoutRef = useRef<ILayoutApi | null>(null);
  const saveTimer = useRef<number | null>(null);
  const [layoutJson, setLayoutJson] = useState<IJsonModel>(() => activeJsonLayout(store.activeLayoutState()));
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [toast, setToast] = useState("");
  const [announcement, setAnnouncement] = useState("Workbench ready");
  const [bottomVisible, setBottomVisible] = useState(true);
  const registry = useMemo(() => new CommandRegistry(), []);

  const panelRegistry = useMemo(
    () =>
      createPanelRegistry({
        explorer: ExplorerPanel,
        "source-discovery": SourceDiscoveryPanel,
        "review-inbox": ReviewInboxPanel,
        git: GitPanel,
        "research-chat": ResearchChatPanel,
        "markdown-editor": MarkdownEditorPanel,
        writing: WritingPanel,
        "pdf-reader": PdfReaderPanel,
        browser: BrowserPanel,
        "citation-evidence": CitationEvidencePanel,
        tasks: TasksPanel,
        exports: ExportPanel,
        settings: SettingsPanel,
        logs: LogsPanel,
        terminal: TerminalPanel,
        problems: ProblemsPanel,
      }),
    [],
  );

  const model = useMemo(() => Model.fromJson(layoutJson), [layoutJson]);

  function announce(message: string) {
    setAnnouncement(message);
    setToast(message);
  }

  function openPanel(id: PanelId, config = {}) {
    const next = openPanelInLayout(layoutJson, id, config);
    setLayoutJson(next);
    store.saveActiveLayout(next);
    announce(`Opened ${panelChrome[id].title}`);
  }

  function closeActivePanel() {
    const next = removeActiveTabFromLayout(layoutJson);
    setLayoutJson(next);
    store.saveActiveLayout(next);
  }

  useEffect(() => {
    registry.registerMany([
      { id: "workbench.palette", title: "Open command palette", run: () => setPaletteOpen(true) },
      { id: "workbench.new-note", title: "New note", run: () => openPanel("markdown-editor") },
      { id: "workbench.shortcuts", title: "Open keyboard shortcuts", run: () => setShortcutsOpen(true) },
      { id: "workbench.toggle-terminal", title: "Toggle bottom panel", run: () => setBottomVisible((current) => !current) },
      { id: "workbench.close-project", title: "Close project", run: () => store.setActiveProject(null) },
      { id: "review.open", title: "Open Review Inbox", run: () => openPanel("review-inbox") },
      { id: "git.init", title: "Initialize Git", disabledReason: "Existing folders require explicit confirmation before Git init.", run: () => undefined },
      { id: "view.reset-layout", title: "View: Reset layout", run: () => resetLayout() },
      { id: "view.save-layout-as", title: "View: Save layout as...", run: () => saveLayoutAs() },
      { id: "view.switch-layout", title: "View: Switch layout", run: () => switchLayout() },
      { id: "workbench.close-active-tab", title: "Close active tab", run: closeActivePanel },
      { id: "workbench.split-editor-tabset", title: "Split active editor tabset", run: () => openPanel("markdown-editor", { fileRef: `split-${Date.now()}` }) },
    ]);
  }, [registry, layoutJson, project.path]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      if ((event.metaKey || event.ctrlKey) && key === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
      if ((event.metaKey || event.ctrlKey) && key === "j") {
        event.preventDefault();
        setBottomVisible((current) => !current);
      }
      if ((event.metaKey || event.ctrlKey) && event.key === "/") {
        event.preventDefault();
        setShortcutsOpen(true);
      }
      if ((event.metaKey || event.ctrlKey) && key === "w") {
        event.preventDefault();
        closeActivePanel();
      }
      if ((event.metaKey || event.ctrlKey) && event.key === "\\") {
        event.preventDefault();
        openPanel("markdown-editor", { fileRef: `split-${Date.now()}` });
      }
      if (event.key === "F6") {
        event.preventDefault();
        document.querySelector<HTMLElement>(".flexlayout__tab_button--selected, .activity-button")?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [layoutJson]);

  function resetLayout() {
    store.resetActiveLayout();
    const next = activeJsonLayout(useWorkspaceStore.getState().activeLayoutState());
    setLayoutJson(next);
    announce("Layout reset");
  }

  function saveLayoutAs() {
    const name = window.prompt("Save layout as", "Research layout");
    if (!name) return;
    store.saveActiveLayoutAs(name, layoutJson);
    announce(`Saved layout ${name}`);
  }

  function switchLayout() {
    const layouts = Object.keys(store.activeLayoutState().layouts);
    const name = window.prompt(`Switch layout (${layouts.join(", ")})`, store.activeLayoutState().activeLayout);
    if (!name) return;
    store.switchActiveLayout(name);
    setLayoutJson(activeJsonLayout(useWorkspaceStore.getState().activeLayoutState()));
  }

  const reviewCount = data.review.data?.counts.pending ?? 0;

  return (
    <div className="workbench-shell">
      <div className="sr-only" aria-live="assertive">{announcement}</div>
      <ActivityBar openPanel={openPanel} reviewCount={reviewCount} />
      <main className="layout-host flexlayout__theme_dark">
        <Layout
          ref={layoutRef}
          model={model}
          factory={(node: TabNode) => {
            const panelId = node.getComponent() as PanelId;
            const panel = panelRegistry[panelId];
            const Component = panel.component;
            return <Component panelId={panelId} config={node.getConfig()} openPanel={openPanel} closeActivePanel={closeActivePanel} announce={announce} />;
          }}
          onRenderTab={(node, renderValues) => {
            const panelId = node.getComponent() as PanelId;
            renderValues.content = <span className="tab-title">{panelChrome[panelId]?.title ?? node.getName()}</span>;
          }}
          onModelChange={(nextModel) => {
            const nextJson = nextModel.toJson();
            setLayoutJson(nextJson);
            if (saveTimer.current) window.clearTimeout(saveTimer.current);
            saveTimer.current = window.setTimeout(() => store.saveActiveLayout(nextJson), 220);
          }}
        />
      </main>
      {bottomVisible ? null : <button className="bottom-reopen" onClick={() => setBottomVisible(true)}><PanelBottom size={14} /> Logs</button>}
      <StatusBar project={project} toast={toast} onReset={resetLayout} onCloseProject={() => store.setActiveProject(null)} />
      {toast && <Toast message={toast} onClose={() => setToast("")} />}
      <CommandPalette
        open={paletteOpen}
        registry={registry}
        onOpenChange={setPaletteOpen}
        onOpenPanel={openPanel}
        onQuickOpen={(type, id, title) => {
          if (type === "note") openPanel("markdown-editor", { noteId: id, title });
          else if (type === "source") openPanel("pdf-reader", { sourceId: id, title });
          else openPanel(type === "task" ? "tasks" : "citation-evidence", { objectId: id, title });
        }}
      />
      <ShortcutReference open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </div>
  );
}

function ActivityBar({ openPanel, reviewCount }: { openPanel: (id: PanelId) => void; reviewCount: number }) {
  const ids: PanelId[] = ["explorer", "source-discovery", "review-inbox", "research-chat", "browser", "writing", "citation-evidence", "tasks", "git", "terminal", "exports", "settings"];
  return (
    <nav className="activity-bar" aria-label="Activity Bar">
      {ids.map((id) => {
        const Icon = panelChrome[id].icon;
        return (
          <button key={id} className="activity-button" onClick={() => openPanel(id)} aria-label={panelChrome[id].title} title={panelChrome[id].title}>
            <Icon size={20} aria-hidden />
            {id === "review-inbox" && reviewCount > 0 && <span className="badge">{reviewCount}</span>}
          </button>
        );
      })}
    </nav>
  );
}

function WelcomeSurface() {
  const setActiveProject = useWorkspaceStore((state) => state.setActiveProject);
  const recentProjects = useWorkspaceStore((state) => state.recentProjects);
  const removeRecentProject = useWorkspaceStore((state) => state.removeRecentProject);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [missing, setMissing] = useState<RecentProject | null>(null);
  const [error, setError] = useState<Error | null>(null);

  async function openBackendProject() {
    setError(null);
    try {
      const tree = await api.get<{ root: string }>("/api/project/tree");
      setActiveProject({ id: "default", path: tree.root, name: tree.root.split("/").pop() || "HydraLab Project" });
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
    }
  }

  return (
    <main className="welcome-shell">
      <section className="welcome-panel">
        <p className="eyebrow">HydraLab</p>
        <h1>Research workbench</h1>
        <div className="welcome-actions" aria-label="Primary project actions">
          <button className="primary-action" onClick={() => setWizardOpen(true)}><Plus size={16} /> Create project</button>
          <button className="primary-action" onClick={() => void openBackendProject()}><FolderOpen size={16} /> Open existing folder</button>
          <section className="recent-list" aria-label="Recent projects">
            <h2>Recent projects</h2>
            {recentProjects.length === 0 ? <p>No recent projects</p> : recentProjects.map((recent) => (
              <button key={recent.path} className="recent-row" onClick={() => (recent.exists === false ? setMissing(recent) : setActiveProject(recent))}>
                <span><strong>{recent.name}</strong><small>{recent.path}</small></span>
                <small>{new Date(recent.lastOpenedAt).toLocaleString()}</small>
              </button>
            ))}
          </section>
        </div>
        <p className="helper-text">Project provisioning through the backend arrives in a later branch if no create route is exposed by this backend.</p>
        {missing && (
          <div className="panel-state failure">
            <strong>folder not found</strong>
            <span>{missing.path}</span>
            <button>Locate folder</button>
            <button onClick={() => removeRecentProject(missing.path)}>Remove from recents</button>
          </div>
        )}
        {error && <div className="panel-state failure"><strong>Open failed</strong><span>{error.message}</span></div>}
      </section>
      {wizardOpen && <ProjectWizard onClose={() => setWizardOpen(false)} onCreate={setActiveProject} />}
    </main>
  );
}

function ProjectWizard({ onClose, onCreate }: { onClose: () => void; onCreate: (project: ActiveProject) => void }) {
  const [name, setName] = useState("");
  const [folder, setFolder] = useState("");
  return (
    <div className="dialog-overlay">
      <form
        className="project-wizard"
        onSubmit={(event) => {
          event.preventDefault();
          onCreate({ id: "default", name: name || "HydraLab Project", path: folder || "local-wizard-project" });
          onClose();
        }}
      >
        <h2>Create project</h2>
        <label>Project name<input value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label>Folder<input value={folder} onChange={(event) => setFolder(event.target.value)} placeholder="Choose folder in the desktop shell" /></label>
        <details>
          <summary>Advanced options</summary>
          <label><input type="checkbox" defaultChecked /> Git init for new HydraLab-created project</label>
          <label><input type="checkbox" defaultChecked /> Offline-first privacy defaults</label>
          <p>Provider setup and Chrome extension pairing remain optional.</p>
        </details>
        <footer><button type="button" onClick={onClose}>Cancel</button><button type="submit">Create project</button></footer>
      </form>
    </div>
  );
}

function StatusBar({ project, toast, onReset, onCloseProject }: { project: ActiveProject; toast: string; onReset: () => void; onCloseProject: () => void }) {
  return (
    <footer className="status-bar">
      <span><CheckCircle2 size={12} /> {project.name}</span>
      <span>{toast || "Idle"}</span>
      <button onClick={onReset}><RotateCcw size={12} /> Reset layout</button>
      <button onClick={onCloseProject}>Close project</button>
    </footer>
  );
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="toast" role="status">
      <span>{message}</span>
      <button onClick={onClose} aria-label="Dismiss notification"><X size={12} /></button>
    </div>
  );
}
