import { describe, expect, test } from "bun:test";
import { activeJsonLayout, defaultLayoutState, migrateWorkspaceState, openPanelInLayout, resetLayout, safeParseWorkspaceState, saveLayoutAs } from "./layout";
import { defaultWorkbenchLayout } from "./panelRegistry";

describe("workspace layout persistence", () => {
  test("round-trips named layouts and active layout", () => {
    const initial = defaultLayoutState();
    const custom = saveLayoutAs(initial, "Focus", openPanelInLayout(defaultWorkbenchLayout(), "markdown-editor", { noteId: "note-1" }));

    expect(custom.activeLayout).toBe("Focus");
    expect(activeJsonLayout(custom).layout).toBeDefined();
  });

  test("migrates legacy persisted shape with default fallback", () => {
    const migrated = migrateWorkspaceState({ version: 0, projects: { "/tmp/project": { activeLayout: "Missing", layouts: {} } } });

    expect(migrated.version).toBe(1);
    expect(migrated.projects["/tmp/project"].layouts.Default).toBeDefined();
  });

  test("falls back on corrupt JSON", () => {
    const parsed = safeParseWorkspaceState("{not-json");

    expect(parsed.projects).toEqual({});
  });

  test("reset restores default layout", () => {
    const changed = saveLayoutAs(defaultLayoutState(), "Custom", openPanelInLayout(defaultWorkbenchLayout(), "browser", { url: "https://example.test" }));
    const reset = resetLayout(changed);

    expect(reset.activeLayout).toBe("Default");
    expect(reset.layouts.Default).toBeDefined();
  });
});

describe("panel open/reveal/reuse", () => {
  test("reuses singleton panel tabs", () => {
    const opened = openPanelInLayout(defaultWorkbenchLayout(), "explorer");
    const reopened = openPanelInLayout(opened, "explorer");

    expect(JSON.stringify(reopened).match(/explorer:singleton/g)?.length).toBe(1);
  });

  test("reuses document tab for the same config and adds a second for different config", () => {
    const one = openPanelInLayout(defaultWorkbenchLayout(), "markdown-editor", { noteId: "a" });
    const same = openPanelInLayout(one, "markdown-editor", { noteId: "a" });
    const different = openPanelInLayout(same, "markdown-editor", { noteId: "b" });
    const serialized = JSON.stringify(different);

    expect(serialized.match(/markdown-editor:a/g)?.length).toBe(1);
    expect(serialized.match(/markdown-editor:b/g)?.length).toBe(1);
  });
});
