import { useEffect, useMemo, useRef, useState } from "react";
import { Actions, DockLocation, Layout, Model, type ILayoutApi, type TabNode } from "flexlayout-react";
import "flexlayout-react/style/dark.css";
import { CheckCircle2, FolderOpen, PanelBottom, Plus, RotateCcw, Save, X } from "lucide-react";
import { api } from "../lib/api";
import { useSurface } from "../lib/responsive";
import { MobileShell } from "../components/mobile/MobileShell";
import { usePhase3MobileSurfaceEnabled } from "../components/mobile/useMobileSurfaceFlag";
import { CommandPalette, ShortcutReference } from "./CommandPalette";
import { CommandRegistry } from "./commands";
import { WorkspaceDataProvider, useWorkspaceData } from "./data";
import { activeJsonLayout } from "./layout";
import { createPanelRegistry, panelChrome, tab, tabStableKey, type PanelConfig, type PanelId, type PanelLocation } from "./panelRegistry";
import { useWorkspaceStore, type ActiveProject, type RecentProject } from "./store";
import { ExplorerPanel } from "./panels/ExplorerPanel";
import { SourceDiscoveryPanel } from "./panels/SourceDiscoveryPanel";
import { ResearchChatPanel } from "./panels/ResearchChatPanel";
import { AgentRunsPanel } from "./panels/AgentRunsPanel";
import { ExperimentsPanel } from "./panels/ExperimentsPanel";
import { IdeaBoardPanel } from "./panels/IdeaBoardPanel";
import { MarkdownEditorPanel } from "./panels/MarkdownEditorPanel";
import { WritingPanel } from "./panels/WritingPanel";
import { TasksPanel } from "./panels/TasksPanel";
import { SelfEvolutionPanel } from "./panels/SelfEvolutionPanel";
import { ReproducibilityPanel } from "./panels/ReproducibilityPanel";
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

// Map a panel's default location to the FlexLayout node the tab is added to.
// center/right target the two named tabsets; border-left/bottom resolve to the
// live border node's id so Actions.addNode drops the tab into the right border.
function resolveAddTarget(model: Model, location: PanelLocation): { toNodeId: string; dock: DockLocation } {
  if (location === "center") return { toNodeId: "center_main", dock: DockLocation.CENTER };
  if (location === "border-right") return { toNodeId: "right_main", dock: DockLocation.CENTER };
  const wanted = location === "border-left" ? "left" : "bottom";
  const border = model.getBorderSet().getBorders().find((node) => node.getLocation().getName() === wanted);
  // Fall back to the center tabset if the border was removed from a custom layout.
  return { toNodeId: border ? border.getId() : "center_main", dock: DockLocation.CENTER };
}

export function WorkbenchRoot() {
  const activeProject = useWorkspaceStore((state) => state.activeProject);
  const surface = useSurface();
  const mobileEnabled = usePhase3MobileSurfaceEnabled();
  // Phase-3 mobile surface: only when the flag is ON and a touch-primary surface is
  // detected. Flag OFF or a desktop surface keeps the existing FlexLayout path
  // byte-for-byte unchanged (HL-UX-30/32). WorkbenchShell itself is never modified.
  const useMobileSurface = mobileEnabled && surface !== "desktop";

  if (!activeProject) return <WelcomeSurface />;
  if (useMobileSurface) {
    return (
      <WorkspaceDataProvider projectId={activeProject.id}>
        <MobileShell project={activeProject} surface={surface} />
      </WorkspaceDataProvider>
    );
  }
  return (
    <WorkspaceDataProvider projectId={activeProject.id}>
      <WorkbenchShell project={activeProject} />
    </WorkspaceDataProvider>
  );
}

function WorkbenchShell({ project }: { project: ActiveProject }) {
  const store = useWorkspaceStore();
  const data = useWorkspaceData();
  const layoutRef = useRef<ILayoutApi | null>(null);
  const saveTimer = useRef<number | null>(null);
  // FlexLayout owns ONE mutable Model for the lifetime of the shell. Recreating
  // it (Model.fromJson) on every onModelChange forced FlexLayout to unmount and
  // remount every panel, wiping each panel's React state on any tab select,
  // resize or drag (the "panel state evaporates" bug). The model is created once;
  // programmatic open/close mutate it in place via Actions; only an explicit
  // reset/switch swaps in a new model (where a remount is expected).
  const [model, setModel] = useState(() => Model.fromJson(activeJsonLayout(store.activeLayoutState())));
  const modelRef = useRef(model);
  useEffect(() => {
    modelRef.current = model;
  }, [model]);
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
        "agent-runs": AgentRunsPanel,
        experiments: ExperimentsPanel,
        "idea-board": IdeaBoardPanel,
        "markdown-editor": MarkdownEditorPanel,
        writing: WritingPanel,
        "pdf-reader": PdfReaderPanel,
        browser: BrowserPanel,
        "citation-evidence": CitationEvidencePanel,
        tasks: TasksPanel,
        exports: ExportPanel,
        reproducibility: ReproducibilityPanel,
        "self-evolution": SelfEvolutionPanel,
        settings: SettingsPanel,
        logs: LogsPanel,
        terminal: TerminalPanel,
        problems: ProblemsPanel,
      }),
    [],
  );

  function announce(message: string) {
    setAnnouncement(message);
    setToast(message);
  }

  function openPanel(id: PanelId, config: PanelConfig = {}) {
    const activeModel = modelRef.current;
    const tabId = tabStableKey(id, config);
    if (activeModel.getNodeById(tabId)) {
      // Already open: just focus it — never rebuild the layout.
      activeModel.doAction(Actions.selectTab(tabId));
    } else {
      const { toNodeId, dock } = resolveAddTarget(activeModel, panelChrome[id].defaultLocation);
      activeModel.doAction(Actions.addNode(tab(id, config), toNodeId, dock, -1, true));
    }
    announce(`Opened ${panelChrome[id].title}`);
  }

  function closeActivePanel() {
    // Close the selected tab of the ACTIVE tabset (what the user is focused on),
    // not the first container found — which previously closed a border tab by
    // mistake (Cmd+W wrong-tab bug).
    const selected = modelRef.current.getActiveTabset()?.getSelectedNode();
    if (selected) modelRef.current.doAction(Actions.deleteTab(selected.getId()));
  }

  useEffect(() => {
    registry.registerMany([
      { id: "workbench.palette", title: "Open command palette", run: () => setPaletteOpen(true) },
      { id: "workbench.new-note", title: "New note", run: () => openPanel("markdown-editor") },
      { id: "workbench.shortcuts", title: "Open keyboard shortcuts", run: () => setShortcutsOpen(true) },
      { id: "workbench.toggle-terminal", title: "Toggle bottom panel", run: () => setBottomVisible((current) => !current) },
      { id: "workbench.close-project", title: "Close project", run: () => store.setActiveProject(null) },
      { id: "review.open", title: "Open Review Inbox", run: () => openPanel("review-inbox") },
      { id: "self-evolution.open", title: "Open Self-Evolution", run: () => openPanel("self-evolution") },
      { id: "git.init", title: "Initialize Git", disabledReason: "Existing folders require explicit confirmation before Git init.", run: () => undefined },
      { id: "view.reset-layout", title: "View: Reset layout", run: () => resetLayout() },
      { id: "view.save-layout-as", title: "View: Save layout as...", run: () => saveLayoutAs() },
      { id: "view.switch-layout", title: "View: Switch layout", run: () => switchLayout() },
      { id: "workbench.close-active-tab", title: "Close active tab", run: closeActivePanel },
      { id: "workbench.split-editor-tabset", title: "Split active editor tabset", run: () => openPanel("markdown-editor", { fileRef: `split-${Date.now()}` }) },
    ]);
  }, [registry, project.path]);

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
  }, []);

  function resetLayout() {
    store.resetActiveLayout();
    setModel(Model.fromJson(activeJsonLayout(useWorkspaceStore.getState().activeLayoutState())));
    announce("Layout reset");
  }

  function saveLayoutAs() {
    const name = window.prompt("Save layout as", "Research layout");
    if (!name) return;
    store.saveActiveLayoutAs(name, modelRef.current.toJson());
    announce(`Saved layout ${name}`);
  }

  function switchLayout() {
    const layouts = Object.keys(store.activeLayoutState().layouts);
    const name = window.prompt(`Switch layout (${layouts.join(", ")})`, store.activeLayoutState().activeLayout);
    if (!name) return;
    store.switchActiveLayout(name);
    setModel(Model.fromJson(activeJsonLayout(useWorkspaceStore.getState().activeLayoutState())));
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
            // Persistence only — never rebuild the model here (that was the
            // remount storm). FlexLayout has already mutated its own model.
            const nextJson = nextModel.toJson();
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
  const ids: PanelId[] = ["explorer", "source-discovery", "review-inbox", "research-chat", "agent-runs", "experiments", "browser", "writing", "citation-evidence", "tasks", "git", "terminal", "exports", "reproducibility", "self-evolution", "settings"];
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
