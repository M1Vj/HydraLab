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

export type PanelUiState = {
  label: "empty" | "loading" | "failure" | "permission-denied";
  purpose?: string;
  cta?: string;
  message?: string;
  cause?: string;
  retryable?: boolean;
};

export type PanelDefinition = {
  id: string;
  title: string;
  activity: string;
  states: {
    empty: PanelUiState;
    loading: PanelUiState;
    failure: PanelUiState;
    permissionDenied: PanelUiState;
  };
};

export type Command = {
  id: string;
  title: string;
  disabledReason?: string;
  run: () => void;
};

export type QuickOpenObject = {
  id: string;
  type: string;
  title: string;
  previousTitles?: string[];
};

export type PaletteActionResult = {
  kind: "action";
  id: string;
  title: string;
  disabledReason?: string;
};

export type PaletteQuickOpenResult = {
  kind: "quick-open";
  objectId: string;
  objectType: string;
  title: string;
};

export type ExplorerViewState = {
  view: "curated" | "raw";
  expandedIds: string[];
};

export type FolderIndexInput = {
  role: string;
  category: "sources" | "code-folder" | "browser-history" | "chat-logs" | "agent-memory" | "large-generated" | string;
  indexPolicy: "auto" | "ask" | "never" | string;
};

export type FolderIndexStatus = "indexed" | "needs-consent" | "excluded";

export type WorkbenchFolder = {
  role: string;
  path: string;
  category: string;
  indexStatus: FolderIndexStatus;
  created: boolean;
};

export type ResearchObject = {
  id: string;
  type: string;
  title: string;
  path?: string;
  linkedIds: string[];
};

export type TrashObject = ResearchObject & {
  deleted: true;
  originalPathKept: true;
  dependentIds: string[];
};

export type ReviewInboxItem = {
  id: string;
  type: string;
  title: string;
  originPanel: string;
};

export type BrowserCaptureControl =
  | "pause"
  | "disable"
  | "reduced-capture"
  | "clear-captured-context"
  | "allowlist"
  | "blocklist";

export type BrowserCaptureSettings = {
  integrationEnabled: boolean;
  g2LocalCapture: boolean;
  browserPageTextToProvider: boolean;
  capturePaused: boolean;
  reducedCapture: boolean;
  connectionStatus: "connected" | "reconnecting" | "backend-stopped" | "handshaking";
  allowedHosts: string[];
  blockedHosts: string[];
  controls: BrowserCaptureControl[];
};

export type InAppBrowserSurface =
  | "iframe"
  | "pdfjs"
  | "snapshot-fallback"
  | "chrome-extension"
  | "playwright";

export type InAppBrowserState =
  | "empty"
  | "loading"
  | "frame-blocked-fallback"
  | "sign-in-required"
  | "automation-ready";

export type BrowserBridgeConnection = {
  status: "connected" | "reconnecting" | "backend-stopped" | "handshaking";
  attempt: number;
  nextDelayMs?: number;
  rereadPortFile?: boolean;
};

export type DiscoveryProviderStatus = {
  provider: string;
  state: "idle" | "loading" | "ready" | "cache-hit" | "error" | "provider rate-limited" | "offline";
  count?: number;
  cacheAgeSeconds?: number;
};

export type DiscoveryResultRow = {
  id: string;
  title: string;
  authors: string[];
  year?: number | null;
  venue: string;
  doi?: string | null;
  pdfAvailable: boolean;
  provider: string;
  expectedSizeBytes?: number | null;
  confidence: number;
  duplicateState?: "unique" | "exact-merged" | "fuzzy-review" | "possible-duplicate";
  cacheAgeSeconds?: number;
};

export type SourceDiscoverySettings = {
  offlineOnly: boolean;
  scholarlyApisEnabled: boolean;
  automaticPdfDownload: boolean;
  allowedPdfDomains: string[];
  largeFileThresholdBytes: number;
};

export const DEFAULT_SOURCE_DISCOVERY_SETTINGS: SourceDiscoverySettings = {
  offlineOnly: false,
  scholarlyApisEnabled: true,
  automaticPdfDownload: false,
  allowedPdfDomains: ["arxiv.org", "openalex.org", "core.ac.uk"],
  largeFileThresholdBytes: 25 * 1024 * 1024,
};

export type WorkbenchProject = {
  id: string;
  name: string;
  folderPath: string;
  template: string;
  folders: WorkbenchFolder[];
  objects: ResearchObject[];
  trash: TrashObject[];
  reviewItems: ReviewInboxItem[];
};

export const DEFAULT_BROWSER_CAPTURE_SETTINGS: BrowserCaptureSettings = {
  integrationEnabled: false,
  g2LocalCapture: false,
  browserPageTextToProvider: false,
  capturePaused: false,
  reducedCapture: false,
  connectionStatus: "backend-stopped",
  allowedHosts: [],
  blockedHosts: [],
  controls: ["pause", "disable", "reduced-capture", "clear-captured-context", "allowlist", "blocklist"],
};

export type WindowProjectState = {
  id: string;
  activeProjectPath: string | null;
};

export type RestoreSettings = {
  restoreOnLaunch: boolean;
};

export type RestoreSession = {
  projectPath: string;
  layout: WorkbenchLayout | null;
};

export type WorkbenchLayout = {
  activeTabs: string[];
};

export const KANBAN_COLUMNS = ["To Do", "In Progress", "Review", "Done"] as const;

export const DEFAULT_PANEL_DEFINITIONS: PanelDefinition[] = [
  panelDefinition("explorer", "Explorer", "explorer", "No sources yet", "Discover sources"),
  panelDefinition("browser", "Browser", "browser", "No browser page open", "Open URL"),
  panelDefinition("source-discovery", "Source Discovery", "sources", "No query run", "Search for papers"),
  panelDefinition("pdf-reader", "PDF Reader", "pdf", "No document open", "Open a PDF"),
  panelDefinition("markdown-editor", "Markdown Editor", "notes", "No note or draft open", "New note"),
  panelDefinition("citation-evidence", "Citation & Evidence", "evidence", "No citations", "Import BibTeX/CSL/RIS"),
  panelDefinition("saved-chat", "Saved Chat", "assistant", "Default project chat empty", "Ask the assistant"),
  panelDefinition("local-search", "Local Search", "search", "No index or no results", "Build index"),
  panelDefinition("git", "Git & Checkpoints", "git", "No repo or clean tree", "Initialize Git"),
  panelDefinition("review-inbox", "Review Inbox", "review", "No pending review items", "All clear"),
  panelDefinition("tasks", "Tasks", "tasks", "Empty board", "Add task"),
];

function panelDefinition(id: string, title: string, activity: string, purpose: string, cta: string): PanelDefinition {
  return {
    id,
    title,
    activity,
    states: {
      empty: { label: "empty", purpose, cta },
      loading: { label: "loading", message: `Loading ${title}` },
      failure: {
        label: "failure",
        message: `${title} could not load`,
        cause: "The panel reported an internal error.",
        retryable: true,
      },
      permissionDenied: {
        label: "permission-denied",
        message: `${title} needs permission`,
        cause: "This action is gated by project or privacy settings.",
      },
    },
  };
}

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

export function resolveInAppBrowserSurface(input: {
  url?: string;
  frameBlocked?: boolean;
  signInRequired?: boolean;
  controlledAutomation?: boolean;
}) {
  if (!input.url) {
    return { surface: "iframe" as InAppBrowserSurface, state: "empty" as InAppBrowserState, blank: false };
  }
  if (input.signInRequired) {
    return {
      surface: "chrome-extension" as InAppBrowserSurface,
      state: "sign-in-required" as InAppBrowserState,
      blank: false,
      action: "Use Chrome extension",
    };
  }
  if (input.controlledAutomation) {
    return { surface: "playwright" as InAppBrowserSurface, state: "automation-ready" as InAppBrowserState, blank: false };
  }
  if (input.frameBlocked) {
    return {
      surface: "snapshot-fallback" as InAppBrowserSurface,
      state: "frame-blocked-fallback" as InAppBrowserState,
      blank: false,
      action: "Open in Chrome extension",
    };
  }
  if (input.url.toLowerCase().split(/[?#]/)[0].endsWith(".pdf")) {
    return { surface: "pdfjs" as InAppBrowserSurface, state: "loading" as InAppBrowserState, blank: false };
  }
  return { surface: "iframe" as InAppBrowserSurface, state: "loading" as InAppBrowserState, blank: false };
}

export function hostPermissionPromptChoices(host: string) {
  return [
    { value: "allow-for-project" as const, label: "Allow for this project", host },
    { value: "always-allow-host" as const, label: "Always allow this host", host },
    { value: "blocked" as const, label: "Decline/Block", host },
  ];
}

export function browserHistoryPermissionRequest(reason: string) {
  return {
    scope: "single-request" as const,
    reason,
    choices: ["Allow for this request", "Decline"],
  };
}

export function shouldShowMainCaptureIndicator(_settings: BrowserCaptureSettings): boolean {
  return false;
}

export function browserProviderEligibility(settings: BrowserCaptureSettings) {
  return {
    localCaptureEnabled: settings.integrationEnabled && settings.g2LocalCapture,
    pageTextProviderEligible: settings.integrationEnabled && settings.g2LocalCapture && settings.browserPageTextToProvider,
    separateOptInRequired: !settings.browserPageTextToProvider,
  };
}

export function nextBrowserBridgeConnection(current: BrowserBridgeConnection, event: "token-rejected" | "request-failed" | "connected" | "max-attempts"): BrowserBridgeConnection {
  if (event === "connected") {
    return { status: "connected", attempt: 0, nextDelayMs: 0, rereadPortFile: false };
  }
  if (event === "max-attempts" || current.attempt >= 10) {
    return { status: "backend-stopped", attempt: current.attempt, rereadPortFile: true };
  }
  const attempt = current.status === "connected" ? 1 : current.attempt + 1;
  return {
    status: "reconnecting",
    attempt,
    nextDelayMs: Math.min(10000, 250 * 2 ** (attempt - 1)),
    rereadPortFile: true,
  };
}

export function resolveDiscoveryPanelState(input: {
  query: string;
  providerStatuses: DiscoveryProviderStatus[];
  results: DiscoveryResultRow[];
  offlineOnly: boolean;
  scholarlyApisEnabled: boolean;
}): "empty" | "loading" | "partial" | "failure" | "offline-permission" | "ready" {
  if (!input.query.trim()) return "empty";
  if (input.offlineOnly || !input.scholarlyApisEnabled) return "offline-permission";
  if (input.providerStatuses.some((status) => status.state === "loading")) return "loading";
  const failures = input.providerStatuses.filter((status) => ["error", "provider rate-limited"].includes(status.state));
  if (failures.length > 0 && input.results.length > 0) return "partial";
  if (failures.length > 0 && failures.length === input.providerStatuses.length) return "failure";
  return input.results.length > 0 ? "ready" : "empty";
}

export function discoveryResultFields(row: DiscoveryResultRow) {
  return {
    title: row.title,
    authors: row.authors.join(", ") || "Unknown authors",
    year: row.year ? String(row.year) : "n.d.",
    venue: row.venue || "Unknown venue",
    doi: row.doi || "No DOI",
    pdf: row.pdfAvailable ? "PDF available" : "No open PDF",
    provider: row.provider,
    expectedSize: row.expectedSizeBytes ? formatBytes(row.expectedSizeBytes) : "Size unknown",
  };
}

export function cacheAgeLabel(seconds?: number): string {
  if (seconds === undefined) return "fresh";
  if (seconds < 60) return `${seconds}s old`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m old`;
  return `${Math.floor(seconds / 3600)}h old`;
}

export function sourceDiscoveryNetworkPosture(settings: SourceDiscoverySettings) {
  if (settings.offlineOnly && !settings.scholarlyApisEnabled) {
    return {
      state: "air-gapped" as const,
      providerCallsAllowed: false,
      message: "Offline-only and scholarly APIs are both disabled.",
    };
  }
  if (settings.offlineOnly) {
    return {
      state: "offline-provider-blocked" as const,
      providerCallsAllowed: true,
      message: "Model-provider sends are blocked; scholarly metadata APIs remain separately allowed.",
    };
  }
  if (!settings.scholarlyApisEnabled) {
    return {
      state: "metadata-apis-disabled" as const,
      providerCallsAllowed: false,
      message: "Scholarly metadata APIs are disabled; cache search only.",
    };
  }
  return {
    state: "online" as const,
    providerCallsAllowed: true,
    message: "Scholarly metadata APIs may be queried under rate limits.",
  };
}

export function pdfDownloadCopy(input: {
  pdfAvailable: boolean;
  expectedSizeBytes?: number | null;
  automaticPdfDownload: boolean;
  thresholdBytes: number;
}) {
  if (!input.pdfAvailable) return "No open-access PDF reported";
  if (!input.automaticPdfDownload) return "PDF waits for explicit save/download";
  if (input.expectedSizeBytes && input.expectedSizeBytes > input.thresholdBytes) {
    return "PDF over size limit; manual download only";
  }
  return "PDF can auto-download from allowed domains";
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${Math.round(bytes / 1024 / 1024)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

export function buildCommandPaletteResults(commands: Command[], objects: QuickOpenObject[], query: string) {
  const normalizedQuery = query.trim().toLowerCase();
  const matches = (text: string) => text.toLowerCase().includes(normalizedQuery);

  return {
    actions: commands
      .map<PaletteActionResult>((command) => ({
        kind: "action",
        id: command.id,
        title: command.title,
        disabledReason: command.disabledReason,
      })),
    quickOpen: objects
      .filter((object) => {
        if (!normalizedQuery) return true;
        return matches(object.title) || object.previousTitles?.some(matches) || matches(object.id);
      })
      .map<PaletteQuickOpenResult>((object) => ({
        kind: "quick-open",
        objectId: object.id,
        objectType: object.type,
        title: object.title,
      })),
  };
}

export function toggleExplorerView(state: ExplorerViewState): ExplorerViewState {
  return {
    ...state,
    view: state.view === "curated" ? "raw" : "curated",
    expandedIds: [...state.expandedIds],
  };
}

export function folderIndexStatus(folder: FolderIndexInput): FolderIndexStatus {
  if (folder.indexPolicy === "never" || folder.category === "large-generated") {
    return "excluded";
  }

  if (
    folder.indexPolicy === "ask" ||
    ["code-folder", "browser-history", "chat-logs", "agent-memory"].includes(folder.category)
  ) {
    return "needs-consent";
  }

  return "indexed";
}

export function createWorkbenchProject(input: {
  name: string;
  folderPath: string;
  template: string;
}): WorkbenchProject {
  const folders: Array<Pick<WorkbenchFolder, "role" | "path" | "category"> & { indexPolicy: string }> = [
    { role: "sources", path: "sources", category: "sources", indexPolicy: "auto" },
    { role: "knowledge", path: "knowledge", category: "notes", indexPolicy: "auto" },
    { role: "work", path: "work", category: "work", indexPolicy: "auto" },
    { role: "writing", path: "writing", category: "writing", indexPolicy: "auto" },
    { role: "outputs", path: "outputs", category: "large-generated", indexPolicy: "never" },
  ];

  return {
    id: stableProjectId(input.folderPath),
    name: input.name,
    folderPath: input.folderPath,
    template: input.template,
    folders: folders.map((folder) => ({
      role: folder.role,
      path: folder.path,
      category: folder.category,
      created: true,
      indexStatus: folderIndexStatus({
        role: folder.role,
        category: folder.category,
        indexPolicy: folder.indexPolicy,
      }),
    })),
    objects: [],
    trash: [],
    reviewItems: [],
  };
}

function stableProjectId(path: string): string {
  const compact = path.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return `project_${compact || "untitled"}`;
}

export function softDeleteObject(project: WorkbenchProject, objectId: string): WorkbenchProject {
  const target = project.objects.find((object) => object.id === objectId);
  if (!target) return project;

  const dependentIds = project.objects.filter((object) => object.linkedIds.includes(objectId)).map((object) => object.id);
  if (target.linkedIds.length > 0) {
    dependentIds.push(...target.linkedIds);
  }

  return {
    ...project,
    objects: project.objects.filter((object) => object.id !== objectId),
    trash: [
      ...project.trash,
      {
        ...target,
        deleted: true,
        originalPathKept: true,
        dependentIds: Array.from(new Set(dependentIds)),
      },
    ],
  };
}

export function restoreTrashObject(project: WorkbenchProject, objectId: string): WorkbenchProject {
  const target = project.trash.find((object) => object.id === objectId);
  if (!target) return project;
  const { deleted: _deleted, originalPathKept: _originalPathKept, dependentIds: _dependentIds, ...object } = target;

  return {
    ...project,
    objects: [...project.objects, object],
    trash: project.trash.filter((trashObject) => trashObject.id !== objectId),
  };
}

export function navigateObjectLink(project: WorkbenchProject, fromObjectId: string, targetObjectId: string) {
  const target = project.objects.find((object) => object.id === targetObjectId);
  if (target) {
    return { state: "resolved", target, actions: ["Go to origin"] };
  }

  const trashed = project.trash.find((object) => object.id === targetObjectId);
  if (trashed) {
    return {
      state: "source trashed",
      target: trashed,
      actions: ["Restore"],
      reviewItem: {
        id: `broken-link-${fromObjectId}-${targetObjectId}`,
        type: "broken-link",
        title: `${fromObjectId} links to a trashed source`,
        originPanel: "citation-evidence",
      },
    };
  }

  return {
    state: "missing",
    actions: ["Review link"],
    reviewItem: {
      id: `missing-link-${fromObjectId}-${targetObjectId}`,
      type: "broken-link",
      title: `${fromObjectId} links to a missing object`,
      originPanel: "review-inbox",
    },
  };
}

export function openProjectInWindow(windowState: WindowProjectState, requestedProjectPath: string) {
  if (windowState.activeProjectPath === requestedProjectPath) {
    return { action: "focus-existing-window" as const, projectPath: requestedProjectPath };
  }
  if (windowState.activeProjectPath) {
    return { action: "new-window" as const, projectPath: requestedProjectPath };
  }
  return { action: "open-in-current-window" as const, projectPath: requestedProjectPath };
}

export function restoreSession(
  settings: RestoreSettings,
  session: RestoreSession | null,
  folderExists: (path: string) => boolean,
) {
  if (!settings.restoreOnLaunch || !session) {
    return { surface: "welcome" as const };
  }

  if (!folderExists(session.projectPath)) {
    return {
      surface: "welcome" as const,
      reason: "folder not found",
      missingProjectPath: session.projectPath,
      layout: defaultWorkbenchLayout(),
    };
  }

  return {
    surface: "workbench" as const,
    projectPath: session.projectPath,
    layout: session.layout ?? defaultWorkbenchLayout(),
  };
}

export function defaultWorkbenchLayout(): WorkbenchLayout {
  return { activeTabs: ["saved-chat", "markdown-editor"] };
}

export type ResearchUndoOperation = {
  label: string;
  before: ResearchObject[];
  after: ResearchObject[];
  editorUndoMarker: string;
};

export function createResearchUndoStack() {
  const undoStack: ResearchUndoOperation[] = [];
  const redoStack: ResearchUndoOperation[] = [];
  let editorMarker = "editor-stack-unchanged";

  return {
    record(operation: ResearchUndoOperation) {
      undoStack.push(operation);
      redoStack.length = 0;
      editorMarker = operation.editorUndoMarker;
    },
    undo() {
      const operation = undoStack.pop();
      if (!operation) return null;
      redoStack.push(operation);
      return { label: operation.label, objects: operation.before.map(cloneResearchObject) };
    },
    redo() {
      const operation = redoStack.pop();
      if (!operation) return null;
      undoStack.push(operation);
      return { label: operation.label, objects: operation.after.map(cloneResearchObject) };
    },
    editorUndoMarker() {
      return editorMarker;
    },
  };
}

function cloneResearchObject(object: ResearchObject): ResearchObject {
  return {
    ...object,
    linkedIds: [...object.linkedIds],
  };
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
