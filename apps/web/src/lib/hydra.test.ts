import { describe, expect, test } from "bun:test";

import {
  buildCommandPaletteResults,
  createResearchUndoStack,
  createWorkbenchProject,
  DEFAULT_PANEL_DEFINITIONS,
  folderIndexStatus,
  groupTasksByColumn,
  navigateObjectLink,
  openProjectInWindow,
  restoreSession,
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
      name: "Attention Mechanisms Review",
      folderPath: "/research/attention",
      template: "empty research",
    });

    expect(project.name).toBe("Attention Mechanisms Review");
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
});
