import { describe, expect, test } from "bun:test";

import {
  buildCommandPaletteResults,
  createResearchUndoStack,
  createWorkbenchProject,
  DEFAULT_PANEL_DEFINITIONS,
  DEFAULT_BROWSER_CAPTURE_SETTINGS,
  DEFAULT_SOURCE_DISCOVERY_SETTINGS,
  browserHistoryPermissionRequest,
  browserProviderEligibility,
  cacheAgeLabel,
  discoveryResultFields,
  folderIndexStatus,
  groupTasksByColumn,
  hostPermissionPromptChoices,
  ingestionConfidenceLabel,
  navigateObjectLink,
  nextBrowserBridgeConnection,
  openProjectInWindow,
  restoreSession,
  resolveIngestionPanelState,
  resolveInAppBrowserSurface,
  resolveDiscoveryPanelState,
  shouldShowMainCaptureIndicator,
  sourceDiscoveryNetworkPosture,
  pdfDownloadCopy,
  softDeleteObject,
  sourceLabel,
  statusCopy,
  toggleExplorerView,
} from "./hydra";

describe("Hydra UI helpers", () => {
  test("formats source labels with author and year traceability", () => {
    expect(sourceLabel({ title: "Graph Search", authors: "A. Researcher", year: "2026" })).toBe(
      "Graph Search - A. Researcher (2026)",
    );
  });

  test("groups tasks into stable Kanban columns", () => {
    const grouped = groupTasksByColumn([
      { id: "1", title: "Read", column: "Done", progress: 100 },
      { id: "2", title: "Draft", column: "To Do", progress: 0 },
    ]);

    expect(grouped.map((column) => column.name)).toEqual(["To Do", "In Progress", "Review", "Done"]);
    expect(grouped[0].tasks[0]?.title).toBe("Draft");
    expect(grouped[3].tasks[0]?.title).toBe("Read");
  });

  test("maps backend status into concise user-facing copy", () => {
    expect(statusCopy("completed")).toBe("Cited answer ready");
    expect(statusCopy("unknown")).toBe("Working");
  });

  test("@HL-UX-02 registers must-keep panels with all four UI states", () => {
    const requiredIds = [
      "explorer",
      "browser",
      "source-discovery",
      "pdf-reader",
      "markdown-editor",
      "citation-evidence",
      "saved-chat",
      "local-search",
      "git",
      "review-inbox",
      "tasks",
    ];

    expect(DEFAULT_PANEL_DEFINITIONS.map((panel) => panel.id)).toEqual(requiredIds);
    for (const panel of DEFAULT_PANEL_DEFINITIONS) {
      expect(panel.states.empty.purpose.length).toBeGreaterThan(0);
      expect(panel.states.loading.label).toBe("loading");
      expect(panel.states.failure.retryable).toBe(true);
      expect(panel.states.permissionDenied.label).toBe("permission-denied");
    }
  });

  test("@HL-UX-03 command palette distinguishes actions from quick-open by stable id after rename", () => {
    const results = buildCommandPaletteResults(
      [
        { id: "workbench.new-note", title: "New note", run: () => undefined },
        { id: "git.init", title: "Initialize Git", disabledReason: "Existing folder requires confirmation", run: () => undefined },
      ],
      [{ id: "note_123", type: "note", title: "Method comparison", previousTitles: ["Draft notes"] }],
      "method",
    );

    expect(results.actions[0].kind).toBe("action");
    expect(results.quickOpen[0]).toMatchObject({ kind: "quick-open", objectId: "note_123", title: "Method comparison" });
    expect(results.actions.find((item) => item.id === "git.init")?.disabledReason).toContain("confirmation");
  });

  test("@HL-UX-07 toggles curated and raw explorer views without losing expansion state", () => {
    const next = toggleExplorerView({ view: "curated", expandedIds: ["sources", "sources/papers"] });

    expect(next.view).toBe("raw");
    expect(next.expandedIds).toEqual(["sources", "sources/papers"]);
  });

  test("@HL-UX-08 maps high-risk folder categories to consent-safe index statuses", () => {
    expect(folderIndexStatus({ role: "sources", category: "sources", indexPolicy: "auto" })).toBe("indexed");
    expect(folderIndexStatus({ role: "repo", category: "code-folder", indexPolicy: "ask" })).toBe("needs-consent");
    expect(folderIndexStatus({ role: "browser", category: "browser-history", indexPolicy: "ask" })).toBe("needs-consent");
    expect(folderIndexStatus({ role: "build", category: "large-generated", indexPolicy: "never" })).toBe("excluded");
  });

  test("@HL-UX-04 @HL-CORE-05 creates a default project with only core folders", () => {
    const project = createWorkbenchProject({
      name: "Workspace Fixture",
      folderPath: "/research/workspace-fixture",
      template: "empty research",
    });

    expect(project.name).toBe("Workspace Fixture");
    expect(project.folders.map((folder) => folder.role)).toEqual(["sources", "knowledge", "work", "writing", "outputs"]);
    expect(project.folders.some((folder) => folder.role.includes("autonomy"))).toBe(false);
  });

  test("@HL-CORE-04 soft-delete moves an object to trash, keeps the file, and restores it", () => {
    const project = createWorkbenchProject({
      name: "Trash Test",
      folderPath: "/research/trash",
      template: "empty research",
    });
    project.objects = [
      { id: "src_1", type: "source", title: "Attention Is All You Need", path: "sources/attention.pdf", linkedIds: ["claim_1"] },
    ];

    const deleted = softDeleteObject(project, "src_1");

    expect(deleted.objects).toHaveLength(0);
    expect(deleted.trash[0]).toMatchObject({ id: "src_1", deleted: true, originalPathKept: true, dependentIds: ["claim_1"] });
  });

  test("@HL-UX-10 resolving a trashed source produces a restore state and Review Inbox warning", () => {
    const project = createWorkbenchProject({ name: "Links", folderPath: "/research/links", template: "empty research" });
    project.objects = [{ id: "claim_1", type: "claim", title: "Self-attention scales quadratically", linkedIds: ["src_1"] }];
    project.trash = [{ id: "src_1", type: "source", title: "Attention Is All You Need", path: "sources/attention.pdf", deleted: true, originalPathKept: true, dependentIds: ["claim_1"] }];

    const result = navigateObjectLink(project, "claim_1", "src_1");

    expect(result.state).toBe("source trashed");
    expect(result.reviewItem?.originPanel).toBe("citation-evidence");
    expect(result.actions).toContain("Restore");
  });

  test("@HL-CORE-01 opening a second project requests a new window", () => {
    const current = { id: "window_1", activeProjectPath: "/research/attention" };

    expect(openProjectInWindow(current, "/research/diffusion")).toEqual({ action: "new-window", projectPath: "/research/diffusion" });
    expect(openProjectInWindow(current, "/research/attention")).toEqual({ action: "focus-existing-window", projectPath: "/research/attention" });
  });

  test("@HL-CORE-02 @HL-CORE-03 session restore skips Welcome only when the folder exists and layout is usable", () => {
    expect(
      restoreSession(
        { restoreOnLaunch: true },
        { projectPath: "/research/attention", layout: { activeTabs: ["pdf-reader"] } },
        (path) => path === "/research/attention",
      ),
    ).toMatchObject({ surface: "workbench", projectPath: "/research/attention", layout: { activeTabs: ["pdf-reader"] } });

    expect(
      restoreSession(
        { restoreOnLaunch: true },
        { projectPath: "/missing", layout: null },
        () => false,
      ),
    ).toMatchObject({ surface: "welcome", missingProjectPath: "/missing", reason: "folder not found" });
  });

  test("@HL-UX-12 research-object undo restores object links without touching editor undo", () => {
    const stack = createResearchUndoStack();

    stack.record({
      label: "Delete claim",
      before: [{ id: "claim_1", type: "claim", title: "Self-attention scales quadratically", linkedIds: ["ev_1"] }],
      after: [],
      editorUndoMarker: "editor-stack-unchanged",
    });

    expect(stack.undo()?.objects[0].linkedIds).toEqual(["ev_1"]);
    expect(stack.editorUndoMarker()).toBe("editor-stack-unchanged");
  });

  test("@HL-BROWSE-03 resolves honest in-app browser surfaces and framing fallback", () => {
    expect(resolveInAppBrowserSurface({ url: "https://example.com/paper", frameBlocked: false })).toMatchObject({
      surface: "iframe",
      state: "loading",
    });
    expect(resolveInAppBrowserSurface({ url: "https://example.com/paper.pdf", frameBlocked: false })).toMatchObject({
      surface: "pdfjs",
      state: "loading",
    });
    expect(resolveInAppBrowserSurface({ url: "https://nature.com/article", frameBlocked: true })).toMatchObject({
      surface: "snapshot-fallback",
      state: "frame-blocked-fallback",
      blank: false,
    });
    expect(resolveInAppBrowserSurface({ url: "https://institution.example/login", signInRequired: true })).toMatchObject({
      surface: "chrome-extension",
      state: "sign-in-required",
    });
  });

  test("@HL-BROWSE-04 host permission prompt exposes exactly three choices", () => {
    expect(hostPermissionPromptChoices("openreview.net")).toEqual([
      { value: "allow-for-project", label: "Allow for this project", host: "openreview.net" },
      { value: "always-allow-host", label: "Always allow this host", host: "openreview.net" },
      { value: "blocked", label: "Decline/Block", host: "openreview.net" },
    ]);
  });

  test("@HL-BROWSE-10 history permission is request scoped with no always-allow option", () => {
    const request = browserHistoryPermissionRequest("Find a paper opened for this answer");

    expect(request.scope).toBe("single-request");
    expect(request.choices).toEqual(["Allow for this request", "Decline"]);
    expect(request.choices.some((choice) => choice.toLowerCase().includes("always"))).toBe(false);
  });

  test("@HL-BROWSE-11 @HL-CONSENT-01 @HL-CONSENT-02 browser capture settings default off and stay Settings-only", () => {
    expect(DEFAULT_BROWSER_CAPTURE_SETTINGS.g2LocalCapture).toBe(false);
    expect(DEFAULT_BROWSER_CAPTURE_SETTINGS.browserPageTextToProvider).toBe(false);
    expect(DEFAULT_BROWSER_CAPTURE_SETTINGS.controls).toEqual([
      "pause",
      "disable",
      "reduced-capture",
      "clear-captured-context",
      "allowlist",
      "blocklist",
    ]);
    expect(shouldShowMainCaptureIndicator(DEFAULT_BROWSER_CAPTURE_SETTINGS)).toBe(false);
    expect(browserProviderEligibility(DEFAULT_BROWSER_CAPTURE_SETTINGS)).toMatchObject({
      localCaptureEnabled: false,
      pageTextProviderEligible: false,
    });
  });

  test("@HL-BROWSE-12 connection reconnect uses capped backoff and backend-stopped state", () => {
    const first = nextBrowserBridgeConnection({ status: "connected", attempt: 0 }, "token-rejected");
    const second = nextBrowserBridgeConnection(first, "request-failed");
    const capped = nextBrowserBridgeConnection({ status: "reconnecting", attempt: 9 }, "request-failed");

    expect(first).toMatchObject({ status: "reconnecting", attempt: 1, rereadPortFile: true });
    expect(second.nextDelayMs).toBeGreaterThan(first.nextDelayMs);
    expect(capped.nextDelayMs).toBeLessThanOrEqual(10000);
    expect(nextBrowserBridgeConnection(capped, "max-attempts")).toMatchObject({ status: "backend-stopped" });
  });

  test("@HL-DISC-05 renders ranked source rows with required metadata fields", () => {
    const fields = discoveryResultFields({
      id: "disc_attention",
      title: "Attention Is All You Need",
      authors: ["Ashish Vaswani", "Noam Shazeer"],
      year: 2017,
      venue: "NeurIPS",
      doi: "10.48550/arXiv.1706.03762",
      pdfAvailable: true,
      provider: "openalex",
      expectedSizeBytes: 4 * 1024 * 1024,
      confidence: 0.94,
    });

    expect(fields).toEqual({
      title: "Attention Is All You Need",
      authors: "Ashish Vaswani, Noam Shazeer",
      year: "2017",
      venue: "NeurIPS",
      doi: "10.48550/arXiv.1706.03762",
      pdf: "PDF available",
      provider: "openalex",
      expectedSize: "4 MB",
    });
  });

  test("@HL-INGEST-07 resolves ingestion panel states and confidence labels", () => {
    expect(resolveIngestionPanelState()).toBe("empty");
    expect(resolveIngestionPanelState({ state: "running", progress: 42, artifacts: [], warnings: [] })).toBe("loading");
    expect(resolveIngestionPanelState({ state: "quarantined", progress: 0, artifacts: [], warnings: [], failureReason: "bad archive" })).toBe("failure");
    expect(resolveIngestionPanelState({ state: "permission-denied", progress: 0, artifacts: [], warnings: [] })).toBe("permission-denied");
    expect(
      resolveIngestionPanelState({
        state: "done",
        progress: 100,
        warnings: ["grobid: unavailable"],
        artifacts: [
          {
            kind: "markdown",
            engine: "docling",
            path: "sources/derived/src/document.md",
            extractionConfidence: 0.923,
            warnings: [],
            trustLevel: "untrusted-external",
          },
        ],
      }),
    ).toBe("ready");
    expect(ingestionConfidenceLabel({ extractionConfidence: 1.4 })).toBe("100%");
  });

  test("@HL-DISC-11 resolves empty, loading, partial, failure and offline discovery states", () => {
    expect(resolveDiscoveryPanelState({ query: "", providerStatuses: [], results: [], offlineOnly: false, scholarlyApisEnabled: true })).toBe("empty");
    expect(resolveDiscoveryPanelState({ query: "attention", providerStatuses: [{ provider: "openalex", state: "loading" }], results: [], offlineOnly: false, scholarlyApisEnabled: true })).toBe("loading");
    expect(resolveDiscoveryPanelState({ query: "attention", providerStatuses: [{ provider: "crossref", state: "ready" }, { provider: "semantic_scholar", state: "error" }], results: [{ id: "1", title: "A", authors: [], venue: "", pdfAvailable: false, provider: "crossref", confidence: 0.7 }], offlineOnly: false, scholarlyApisEnabled: true })).toBe("partial");
    expect(resolveDiscoveryPanelState({ query: "attention", providerStatuses: [{ provider: "openalex", state: "error" }], results: [], offlineOnly: false, scholarlyApisEnabled: true })).toBe("failure");
    expect(resolveDiscoveryPanelState({ query: "attention", providerStatuses: [], results: [], offlineOnly: true, scholarlyApisEnabled: false })).toBe("offline-permission");
  });

  test("@HL-BROWSE-04 offline-only has a separate scholarly API air-gap toggle", () => {
    expect(sourceDiscoveryNetworkPosture(DEFAULT_SOURCE_DISCOVERY_SETTINGS)).toMatchObject({ state: "online", providerCallsAllowed: true });
    expect(sourceDiscoveryNetworkPosture({ ...DEFAULT_SOURCE_DISCOVERY_SETTINGS, offlineOnly: true })).toMatchObject({
      state: "offline-provider-blocked",
      providerCallsAllowed: true,
    });
    expect(sourceDiscoveryNetworkPosture({ ...DEFAULT_SOURCE_DISCOVERY_SETTINGS, offlineOnly: true, scholarlyApisEnabled: false })).toMatchObject({
      state: "air-gapped",
      providerCallsAllowed: false,
    });
  });

  test("@HL-DISC-08 @HL-DISC-09 shows cache age and explicit PDF policy copy", () => {
    expect(cacheAgeLabel(90)).toBe("1m old");
    expect(pdfDownloadCopy({ pdfAvailable: true, automaticPdfDownload: false, thresholdBytes: 25 * 1024 * 1024 })).toBe(
      "PDF waits for explicit save/download",
    );
    expect(pdfDownloadCopy({ pdfAvailable: true, automaticPdfDownload: true, expectedSizeBytes: 30 * 1024 * 1024, thresholdBytes: 25 * 1024 * 1024 })).toBe(
      "PDF over size limit; manual download only",
    );
  });
});
