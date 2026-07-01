import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArchiveRestore,
  Bell,
  BookOpenCheck,
  CheckCircle2,
  ChevronRight,
  Command,
  FileSearch,
  FileText,
  FolderOpen,
  GitBranch,
  Inbox,
  LayoutPanelLeft,
  Library,
  ListTodo,
  MessageSquareText,
  Plus,
  RotateCcw,
  Search,
  Settings,
  SplitSquareHorizontal,
  Terminal,
  Trash2,
  X,
} from "lucide-react";

import "./styles.css";
import { commandRegistry } from "./core/commands";
import {
  createResearchUndoStack,
  createWorkbenchProject,
  DEFAULT_PANEL_DEFINITIONS,
  defaultWorkbenchLayout,
  folderIndexStatus,
  navigateObjectLink,
  openProjectInWindow,
  restoreSession,
  restoreTrashObject,
  softDeleteObject,
  type ExplorerViewState,
  type PanelDefinition,
  type ResearchObject,
  type ReviewInboxItem,
  type WorkbenchProject,
} from "./lib/hydra";
import { Dialog, DropdownMenu, Switch, Tooltip } from "./components/ui/primitives";

type Surface = "welcome" | "workbench";
type PanelStateKind = "empty" | "loading" | "failure" | "permission-denied";

const recentProjects = [
  {
    name: "Transformer Survey",
    path: "/Users/vjmabansag/Research/Transformer Survey",
    lastOpened: "Yesterday",
    exists: false,
  },
  {
    name: "Attention Mechanisms Review",
    path: "/Users/vjmabansag/Research/Attention Mechanisms Review",
    lastOpened: "Today",
    exists: true,
  },
];

const initialProject = seedProject();

function seedProject(): WorkbenchProject {
  const project = createWorkbenchProject({
    name: "Attention Mechanisms Review",
    folderPath: "/Users/vjmabansag/Research/Attention Mechanisms Review",
    template: "empty research",
  });
  project.folders.push(
    {
      role: "code-folder",
      path: "work/code",
      category: "code-folder",
      created: true,
      indexStatus: folderIndexStatus({ role: "code-folder", category: "code-folder", indexPolicy: "ask" }),
    },
    {
      role: "browser-history",
      path: ".hydralab/browser",
      category: "browser-history",
      created: true,
      indexStatus: folderIndexStatus({ role: "browser-history", category: "browser-history", indexPolicy: "ask" }),
    },
  );
  project.objects = [
    {
      id: "src_attention",
      type: "source",
      title: "Attention Is All You Need",
      path: "sources/attention.pdf",
      linkedIds: ["claim_attention"],
    },
    {
      id: "note_method",
      type: "note",
      title: "Method comparison",
      path: "knowledge/method-comparison.md",
      linkedIds: ["src_attention"],
    },
    {
      id: "claim_attention",
      type: "claim",
      title: "Self-attention scales quadratically",
      path: "knowledge/claims/self-attention.md",
      linkedIds: ["src_attention"],
    },
  ];
  project.reviewItems = [
    { id: "review_source", type: "captured source", title: "Captured source candidate", originPanel: "explorer" },
    { id: "review_claim", type: "suggested claim", title: "Suggested claim needs evidence", originPanel: "citation-evidence" },
    { id: "review_memory", type: "memory candidate", title: "Project context update", originPanel: "saved-chat" },
  ];
  return project;
}

function WorkbenchApp() {
  const restored = restoreSession(
    { restoreOnLaunch: true },
    { projectPath: initialProject.folderPath, layout: defaultWorkbenchLayout() },
    (path) => path === initialProject.folderPath,
  );
  const [surface, setSurface] = useState<Surface>(restored.surface === "workbench" ? "workbench" : "welcome");
  const [project, setProject] = useState<WorkbenchProject | null>(restored.surface === "workbench" ? initialProject : null);
  const [missingRecent, setMissingRecent] = useState<(typeof recentProjects)[number] | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutOpen, setShortcutOpen] = useState(false);
  const [activeActivity, setActiveActivity] = useState("explorer");
  const [activeTab, setActiveTab] = useState("saved-chat");
  const [splitTab, setSplitTab] = useState("citation-evidence");
  const [bottomOpen, setBottomOpen] = useState(true);
  const [explorerState, setExplorerState] = useState<ExplorerViewState>({ view: "curated", expandedIds: ["sources"] });
  const [panelState, setPanelState] = useState<Record<string, PanelStateKind>>({});
  const [toast, setToast] = useState("Session restored from last-good layout");
  const [announcement, setAnnouncement] = useState("Workbench ready");
  const undoStack = useMemo(() => createResearchUndoStack(), []);

  useEffect(() => {
    commandRegistry.register({ id: "workbench.palette", title: "Open command palette", run: () => setPaletteOpen(true) });
    commandRegistry.register({ id: "workbench.new-note", title: "New note", run: () => createOnDemandNote() });
    commandRegistry.register({ id: "workbench.shortcuts", title: "Open keyboard shortcuts", run: () => setShortcutOpen(true) });
    commandRegistry.register({ id: "workbench.toggle-terminal", title: "Toggle terminal/log panel", run: () => setBottomOpen((open) => !open) });
    commandRegistry.register({ id: "workbench.close-project", title: "Close project", run: () => closeProject() });
    commandRegistry.register({ id: "review.open", title: "Open Review Inbox", run: () => setActiveActivity("review-inbox") });
    commandRegistry.register({
      id: "git.init",
      title: "Initialize Git",
      disabledReason: "Existing folders require explicit confirmation before Git init.",
      run: () => undefined,
    });
    for (const object of initialProject.objects) {
      commandRegistry.registerQuickOpen({ id: object.id, type: object.type, title: object.title, previousTitles: ["Draft notes"] });
    }
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "j") {
        event.preventDefault();
        setBottomOpen((open) => !open);
      }
      if ((event.metaKey || event.ctrlKey) && event.key === "/") {
        event.preventDefault();
        setShortcutOpen(true);
      }
      if (event.key === "F6") {
        event.preventDefault();
        setActiveActivity((activity) => (activity === "explorer" ? "saved-chat" : "explorer"));
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function createOnDemandNote() {
    setProject((current) => {
      if (!current) return current;
      const hasNotes = current.folders.some((folder) => folder.role === "notes");
      const folders = hasNotes
        ? current.folders
        : [
            ...current.folders,
            {
              role: "notes",
              path: "knowledge/notes",
              category: "notes",
              created: true,
              indexStatus: "indexed" as const,
            },
          ];
      return {
        ...current,
        folders,
        objects: [
          ...current.objects,
          {
            id: `note_${current.objects.length + 1}`,
            type: "note",
            title: "New note",
            path: "knowledge/notes/new-note.md",
            linkedIds: [],
          },
        ],
      };
    });
    setActiveTab("markdown-editor");
    setToast("Created note and surfaced the on-demand notes folder");
  }

  function openProject(path: string) {
    const decision = openProjectInWindow({ id: "window_1", activeProjectPath: project?.folderPath ?? null }, path);
    if (decision.action === "new-window") {
      setToast("Opening a second project in a new window");
      setAnnouncement("Second project opens in a new window; current project remains active");
      return;
    }
    setProject(initialProject);
    setSurface("workbench");
  }

  function closeProject() {
    setProject(null);
    setSurface("welcome");
    setToast("");
  }

  function deleteSource() {
    if (!project) return;
    undoStack.record({
      label: "Delete source",
      before: project.objects,
      after: project.objects.filter((object) => object.id !== "src_attention"),
      editorUndoMarker: "editor-stack-unchanged",
    });
    const next = softDeleteObject(project, "src_attention");
    const linkResult = navigateObjectLink(next, "claim_attention", "src_attention");
    setProject({
      ...next,
      reviewItems: linkResult.reviewItem ? [...next.reviewItems, linkResult.reviewItem as ReviewInboxItem] : next.reviewItems,
    });
    setActiveTab("citation-evidence");
    setToast("Moved source to Trash. Original file remains on disk.");
  }

  function restoreSource() {
    if (!project) return;
    setProject(restoreTrashObject(project, "src_attention"));
    setToast("Restored source from Trash");
  }

  function undoResearchOperation() {
    const undo = undoStack.undo();
    if (!undo || !project) return;
    setProject({ ...project, objects: undo.objects as ResearchObject[] });
    setToast("Research-object undo restored prior links; editor undo stack unchanged");
  }

  if (surface === "welcome" || !project) {
    return (
      <>
        <WelcomeSurface
          missingRecent={missingRecent}
          onCreate={() => setWizardOpen(true)}
          onOpen={() => openProject(initialProject.folderPath)}
          onRecent={(recent) => {
            if (!recent.exists) setMissingRecent(recent);
            else openProject(recent.path);
          }}
          onRemoveMissing={() => setMissingRecent(null)}
        />
        <ProjectWizard
          open={wizardOpen}
          onClose={() => setWizardOpen(false)}
          onCreate={(nextProject) => {
            setProject(nextProject);
            setSurface("workbench");
            setWizardOpen(false);
          }}
        />
      </>
    );
  }

  const activePanel = DEFAULT_PANEL_DEFINITIONS.find((panel) => panel.id === activeActivity) ?? DEFAULT_PANEL_DEFINITIONS[0];
  const reviewCount = project.reviewItems.filter((item) => item.type !== "accepted").length;

  return (
    <div className="workbench-shell">
      <div className="sr-only" aria-live="assertive">
        {announcement}
      </div>
      <ActivityBar active={activeActivity} reviewCount={reviewCount} onSelect={setActiveActivity} />
      <aside className="sidebar-panel">
        <PanelHeader title={activePanel.title} state={panelState[activePanel.id] ?? "empty"} onState={setPanelStateFor(activePanel.id)} />
        <PanelContent
          panel={activePanel}
          state={panelState[activePanel.id] ?? "empty"}
          project={project}
          explorerState={explorerState}
          onExplorerState={setExplorerState}
          onCreateNote={createOnDemandNote}
          onDeleteSource={deleteSource}
          onRestoreSource={restoreSource}
          onOpenReview={() => setActiveActivity("review-inbox")}
        />
      </aside>
      <main className="workspace-main">
        <div className="editor-tabs" role="tablist" aria-label="Open panels">
          {["saved-chat", "markdown-editor", "citation-evidence", "tasks"].map((tab) => (
            <button
              key={tab}
              className={`editor-tab ${activeTab === tab ? "active" : ""}`}
              draggable
              onDragStart={(event) => event.dataTransfer.setData("text/plain", tab)}
              onClick={() => setActiveTab(tab)}
              role="tab"
              aria-selected={activeTab === tab}
            >
              {tabTitle(tab)}
              <X size={12} aria-hidden="true" />
            </button>
          ))}
          <button
            className="editor-tab icon-tab"
            onClick={() => setSplitTab(splitTab === "citation-evidence" ? "pdf-reader" : "citation-evidence")}
            aria-label="Split editor group"
          >
            <SplitSquareHorizontal size={14} />
          </button>
        </div>
        <div className="split-workspace" onDrop={(event) => setSplitTab(event.dataTransfer.getData("text/plain"))} onDragOver={(event) => event.preventDefault()}>
          <section className="editor-surface" tabIndex={0}>
            <ObjectPanel panelId={activeTab} project={project} onCreateNote={createOnDemandNote} onUndo={undoResearchOperation} />
          </section>
          <section className="editor-surface secondary" tabIndex={0}>
            <ObjectPanel panelId={splitTab} project={project} onCreateNote={createOnDemandNote} onUndo={undoResearchOperation} />
          </section>
        </div>
        {bottomOpen && <BottomPanel />}
      </main>
      <StatusBar
        toast={toast}
        onToggleBottom={() => setBottomOpen((open) => !open)}
        onOpenShortcuts={() => setShortcutOpen(true)}
        onCloseProject={closeProject}
      />
      <Toast message={toast} onClose={() => setToast("")} />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onGoTo={(id) => {
        setActiveTab(id.startsWith("note") ? "markdown-editor" : "citation-evidence");
        setToast(`Quick-open resolved stable object id ${id}`);
      }} />
      <ProjectWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onCreate={(nextProject) => {
          setProject(nextProject);
          setWizardOpen(false);
        }}
      />
      <ShortcutReference open={shortcutOpen} onClose={() => setShortcutOpen(false)} />
    </div>
  );

  function setPanelStateFor(panelId: string) {
    return (state: PanelStateKind) => setPanelState((current) => ({ ...current, [panelId]: state }));
  }
}

function WelcomeSurface({
  missingRecent,
  onCreate,
  onOpen,
  onRecent,
  onRemoveMissing,
}: {
  missingRecent: (typeof recentProjects)[number] | null;
  onCreate: () => void;
  onOpen: () => void;
  onRecent: (recent: (typeof recentProjects)[number]) => void;
  onRemoveMissing: () => void;
}) {
  return (
    <main className="welcome-shell">
      <section className="welcome-panel">
        <p className="eyebrow">HydraLab</p>
        <h1>Research workbench</h1>
        <div className="welcome-actions" aria-label="Primary project actions">
          <button className="primary-action" onClick={onCreate}>
            <Plus size={16} /> Create project
          </button>
          <button className="primary-action" onClick={onOpen}>
            <FolderOpen size={16} /> Open existing folder
          </button>
          <section className="recent-list" aria-label="Recent projects">
            <h2>Recent projects</h2>
            {recentProjects.map((recent) => (
              <button key={recent.path} className="recent-row" onClick={() => onRecent(recent)}>
                <span>
                  <strong>{recent.name}</strong>
                  <small>{recent.path}</small>
                </span>
                <span className={recent.exists ? "status-pill indexed" : "status-pill warning"}>
                  {recent.exists ? recent.lastOpened : "folder not found"}
                </span>
              </button>
            ))}
          </section>
        </div>
        {missingRecent && (
          <div className="inline-state failure" role="alert">
            <strong>folder not found</strong>
            <span>{missingRecent.path}</span>
            <div className="row-actions">
              <button>Locate folder</button>
              <button onClick={onRemoveMissing}>Remove from recents</button>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}

function ProjectWizard({
  open,
  onClose,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (project: WorkbenchProject) => void;
}) {
  const [name, setName] = useState("Attention Mechanisms Review");
  const [folder, setFolder] = useState("/Users/vjmabansag/Research/Attention Mechanisms Review");
  const [template, setTemplate] = useState("empty research");
  const [advanced, setAdvanced] = useState(false);
  const [gitInit, setGitInit] = useState(true);

  return (
    <Dialog open={open} title="Create project" onClose={onClose}>
      <div className="wizard-grid">
        <label className="ui-field">
          <span>Project name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label className="ui-field">
          <span>Folder</span>
          <input value={folder} onChange={(event) => setFolder(event.target.value)} />
        </label>
        <DropdownMenu
          label="Template"
          value={template}
          onChange={setTemplate}
          options={[
            { value: "empty research", label: "empty research" },
            { value: "literature review", label: "literature review" },
          ]}
        />
        <Switch checked={advanced} onChange={setAdvanced} label="Advanced options" />
        {advanced && (
          <div className="advanced-grid">
            <DropdownMenu
              label="Project type"
              value="paper review"
              onChange={() => undefined}
              options={[{ value: "paper review", label: "paper review" }]}
            />
            <label className="ui-field">
              <span>Citation style hint</span>
              <input defaultValue="APA" />
            </label>
            <label className="ui-field">
              <span>Manuscript format hint</span>
              <input defaultValue="Markdown first" />
            </label>
            <Switch checked={gitInit} onChange={setGitInit} label="Git init for new HydraLab-created project" />
            <p className="helper-text">Offline-first privacy defaults stay enabled. Chrome extension and provider setup remain optional.</p>
          </div>
        )}
      </div>
      <footer className="dialog-actions">
        <button onClick={onClose}>Cancel</button>
        <button
          className="accent-button"
          onClick={() => onCreate(createWorkbenchProject({ name, folderPath: folder, template }))}
        >
          Create project
        </button>
      </footer>
    </Dialog>
  );
}

function ActivityBar({ active, reviewCount, onSelect }: { active: string; reviewCount: number; onSelect: (id: string) => void }) {
  const items = [
    ["explorer", LayoutPanelLeft, "Explorer"],
    ["saved-chat", MessageSquareText, "Assistant"],
    ["source-discovery", FileSearch, "Source discovery"],
    ["citation-evidence", BookOpenCheck, "Citation and evidence"],
    ["review-inbox", Inbox, "Review Inbox"],
    ["tasks", ListTodo, "Tasks"],
    ["git", GitBranch, "Git"],
    ["settings", Settings, "Settings"],
  ] as const;

  return (
    <nav className="activity-bar" aria-label="Activity Bar">
      {items.map(([id, Icon, label]) => (
        <Tooltip key={id} label={label}>
          <button className={`activity-button ${active === id ? "active" : ""}`} onClick={() => onSelect(id)} aria-label={label}>
            <Icon size={20} />
            {id === "review-inbox" && reviewCount > 0 && <span className="badge">{reviewCount}</span>}
          </button>
        </Tooltip>
      ))}
    </nav>
  );
}

function PanelHeader({ title, state, onState }: { title: string; state: PanelStateKind; onState: (state: PanelStateKind) => void }) {
  return (
    <header className="panel-header">
      <strong>{title}</strong>
      <select value={state} onChange={(event) => onState(event.target.value as PanelStateKind)} aria-label="Panel state">
        <option value="empty">empty</option>
        <option value="loading">loading</option>
        <option value="failure">failure</option>
        <option value="permission-denied">permission-denied</option>
      </select>
    </header>
  );
}

function PanelContent({
  panel,
  state,
  project,
  explorerState,
  onExplorerState,
  onCreateNote,
  onDeleteSource,
  onRestoreSource,
  onOpenReview,
}: {
  panel: PanelDefinition;
  state: PanelStateKind;
  project: WorkbenchProject;
  explorerState: ExplorerViewState;
  onExplorerState: (state: ExplorerViewState) => void;
  onCreateNote: () => void;
  onDeleteSource: () => void;
  onRestoreSource: () => void;
  onOpenReview: () => void;
}) {
  if (state !== "empty") return <PanelStateView panel={panel} state={state} />;
  if (panel.id === "explorer") {
    return (
      <ExplorerPanel
        project={project}
        explorerState={explorerState}
        onExplorerState={onExplorerState}
        onCreateNote={onCreateNote}
        onDeleteSource={onDeleteSource}
        onRestoreSource={onRestoreSource}
      />
    );
  }
  if (panel.id === "review-inbox") return <ReviewInboxPanel project={project} onOpenReview={onOpenReview} />;
  return <PanelEmpty panel={panel} />;
}

function PanelStateView({ panel, state }: { panel: PanelDefinition; state: PanelStateKind }) {
  if (state === "loading") {
    return (
      <div className="panel-body">
        <div className="skeleton" aria-busy="true" aria-label={panel.states.loading.message} />
        <div className="skeleton short" />
      </div>
    );
  }
  const model = state === "failure" ? panel.states.failure : panel.states.permissionDenied;
  return (
    <div className={`inline-state ${state === "failure" ? "failure" : "permission"}`} role="alert">
      <strong>{model.message}</strong>
      <span>{model.cause}</span>
      {state === "failure" ? <button>Retry</button> : <button>Open Settings</button>}
    </div>
  );
}

function PanelEmpty({ panel }: { panel: PanelDefinition }) {
  return (
    <div className="empty-panel">
      <p>{panel.states.empty.purpose}</p>
      <button>{panel.states.empty.cta}</button>
    </div>
  );
}

function ExplorerPanel({
  project,
  explorerState,
  onExplorerState,
  onCreateNote,
  onDeleteSource,
  onRestoreSource,
}: {
  project: WorkbenchProject;
  explorerState: ExplorerViewState;
  onExplorerState: (state: ExplorerViewState) => void;
  onCreateNote: () => void;
  onDeleteSource: () => void;
  onRestoreSource: () => void;
}) {
  const visibleObjects = project.objects.filter((object) => object.type !== "future-autonomy");

  return (
    <div className="panel-body">
      <div className="toolbar">
        <button
          onClick={() => onExplorerState({ ...explorerState, view: explorerState.view === "curated" ? "raw" : "curated" })}
        >
          {explorerState.view === "curated" ? "Curated" : "Raw files"}
        </button>
        <button onClick={onCreateNote}>
          <Plus size={13} /> New note
        </button>
      </div>
      <div className="tree-list" aria-label={`${explorerState.view} explorer`}>
        {project.folders.map((folder) => (
          <div key={folder.role} className="tree-row">
            <ChevronRight size={13} />
            <span>{explorerState.view === "curated" ? folder.role : folder.path}</span>
            <span className={`status-pill ${folder.indexStatus}`}>{folder.indexStatus}</span>
          </div>
        ))}
        {visibleObjects.map((object) => (
          <div key={object.id} className="tree-row object-row">
            {object.type === "source" ? <Library size={13} /> : <FileText size={13} />}
            <span>{explorerState.view === "curated" ? object.title : object.path}</span>
            {object.type === "source" && (
              <button className="mini-button" onClick={onDeleteSource}>
                <Trash2 size={12} /> Delete
              </button>
            )}
          </div>
        ))}
        {project.trash.length > 0 && (
          <section className="trash-box">
            <strong>Trash</strong>
            {project.trash.map((object) => (
              <div key={object.id} className="tree-row">
                <Trash2 size={13} />
                <span>{object.title}</span>
                <button className="mini-button" onClick={onRestoreSource}>
                  <ArchiveRestore size={12} /> Restore
                </button>
              </div>
            ))}
          </section>
        )}
      </div>
      <p className="helper-text">Raw create, rename and move operations are routed through the backend. Delete is soft-delete only.</p>
    </div>
  );
}

function ReviewInboxPanel({ project }: { project: WorkbenchProject; onOpenReview: () => void }) {
  if (project.reviewItems.length === 0) return <div className="empty-panel"><p>All clear</p></div>;
  return (
    <div className="panel-body">
      {project.reviewItems.map((item) => (
        <div className="review-row" key={item.id}>
          <span className="origin-badge">{item.originPanel}</span>
          <strong>{item.title}</strong>
          <small>{item.type}</small>
        </div>
      ))}
    </div>
  );
}

function ObjectPanel({
  panelId,
  project,
  onCreateNote,
  onUndo,
}: {
  panelId: string;
  project: WorkbenchProject;
  onCreateNote: () => void;
  onUndo: () => void;
}) {
  if (panelId === "markdown-editor") {
    return (
      <article className="object-panel">
        <header>
          <FileText size={16} />
          <strong>Method comparison</strong>
        </header>
        <textarea defaultValue={"# Method comparison\n\nUse [[Attention Is All You Need]] to connect notes, claims and evidence."} />
        <div className="link-strip">
          <span>Backlinks: Attention Is All You Need</span>
          <span>Forward links: Self-attention scales quadratically</span>
        </div>
        <button onClick={onCreateNote}>New note</button>
      </article>
    );
  }
  if (panelId === "citation-evidence") {
    const trashed = project.trash.find((object) => object.id === "src_attention");
    return (
      <article className="object-panel">
        <header>
          <BookOpenCheck size={16} />
          <strong>Citation & Evidence</strong>
          <button onClick={onUndo}>
            <RotateCcw size={13} /> Undo object operation
          </button>
        </header>
        <div className={trashed ? "source-trashed" : "evidence-card"}>
          <strong>{trashed ? "source trashed" : "Self-attention scales quadratically"}</strong>
          <p>{trashed ? "The linked source is in Trash. Restore keeps the evidence graph recoverable." : "go-to-origin: sources/attention.pdf#page=5"}</p>
          <button>{trashed ? "Restore" : "Go to origin"}</button>
        </div>
      </article>
    );
  }
  if (panelId === "tasks") {
    return (
      <article className="object-panel">
        <header>
          <ListTodo size={16} />
          <strong>Tasks</strong>
        </header>
        <div className="kanban-grid">
          {["To Do", "In Progress", "Review", "Done"].map((column) => (
            <section key={column}>
              <h3>{column}</h3>
              <button>Add task</button>
            </section>
          ))}
        </div>
      </article>
    );
  }
  return (
    <article className="object-panel">
      <header>
        <MessageSquareText size={16} />
        <strong>Saved chat assistant</strong>
      </header>
      <div className="empty-panel">
        <p>Default project chat empty</p>
        <button>Ask the assistant</button>
      </div>
    </article>
  );
}

function BottomPanel() {
  return (
    <section className="bottom-panel">
      <header className="bottom-tabs">
        <span>Logs</span>
        <span>Output</span>
        <span>Problems</span>
      </header>
      <pre>{`backend readyz: ready\nindexing: idle\nprovider: offline-first\nsafe console: verification allowlist only`}</pre>
    </section>
  );
}

function StatusBar({
  toast,
  onToggleBottom,
  onOpenShortcuts,
  onCloseProject,
}: {
  toast: string;
  onToggleBottom: () => void;
  onOpenShortcuts: () => void;
  onCloseProject: () => void;
}) {
  return (
    <footer className="status-bar">
      <button onClick={onToggleBottom}>
        <Terminal size={12} /> Logs
      </button>
      <span>
        <CheckCircle2 size={12} /> 0 Errors
      </span>
      <span>
        <Bell size={12} /> {toast || "Idle"}
      </span>
      <button onClick={onCloseProject}>Close project</button>
      <button onClick={onOpenShortcuts}>Shortcuts</button>
    </footer>
  );
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  if (!message) return null;
  return (
    <div className="toast" role="status">
      <span>{message}</span>
      <button onClick={onClose} aria-label="Dismiss notification">
        <X size={12} />
      </button>
    </div>
  );
}

function CommandPalette({ open, onClose, onGoTo }: { open: boolean; onClose: () => void; onGoTo: (id: string) => void }) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const results = commandRegistry.search(query);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  return (
    <Dialog open={open} title="Command palette" onClose={onClose}>
      <div className="palette">
        <label className="ui-field">
          <span>Action or go-to</span>
          <input ref={inputRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search commands, notes, sources..." />
        </label>
        <section>
          <h3>Actions</h3>
          {results.actions.map((action) => (
            <button
              key={action.id}
              className="palette-row"
              disabled={Boolean(action.disabledReason)}
              onClick={() => {
                commandRegistry.run(action.id);
                onClose();
              }}
            >
              <Command size={13} />
              <span>{action.title}</span>
              {action.disabledReason && <small>{action.disabledReason}</small>}
            </button>
          ))}
        </section>
        <section>
          <h3>Quick-open</h3>
          {results.quickOpen.map((object) => (
            <button
              key={object.objectId}
              className="palette-row quick"
              onClick={() => {
                onGoTo(object.objectId);
                onClose();
              }}
            >
              <Search size={13} />
              <span>{object.title}</span>
              <small>{object.objectId}</small>
            </button>
          ))}
        </section>
      </div>
    </Dialog>
  );
}

function ShortcutReference({ open, onClose }: { open: boolean; onClose: () => void }) {
  const shortcuts = [
    ["palette-open", "Command-K"],
    ["quick-open/go-to", "Command-P"],
    ["save", "Command-S"],
    ["new note/draft", "Command-N"],
    ["toggle explorer/assistant/browser/terminal", "Command-1..4 / Command-J"],
    ["focus-next-panel", "F6"],
    ["search", "Command-F"],
    ["citation-picker", "Command-Shift-C"],
    ["Review Inbox", "Command-Shift-R"],
  ];

  return (
    <Dialog open={open} title="Keyboard shortcuts" onClose={onClose}>
      <div className="shortcut-table">
        {shortcuts.map(([name, key]) => (
          <div key={name}>
            <span>{name}</span>
            <kbd>{key}</kbd>
          </div>
        ))}
      </div>
    </Dialog>
  );
}

function tabTitle(id: string) {
  const titles: Record<string, string> = {
    "saved-chat": "Research Chat",
    "markdown-editor": "Draft Notes.md",
    "citation-evidence": "Evidence",
    tasks: "Kanban",
    "pdf-reader": "PDF Reader",
  };
  return titles[id] ?? id;
}

function App() {
  return <WorkbenchApp />;
}

createRoot(document.getElementById("root")!).render(<App />);
