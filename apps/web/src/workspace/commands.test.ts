import { describe, expect, test } from "bun:test";
import { buildPaletteResults, CommandRegistry, quickOpenFromObjects } from "./commands";

describe("command palette search", () => {
  test("includes disabled commands with reasons", () => {
    const registry = new CommandRegistry();
    registry.register({ id: "git.init", title: "Initialize Git", disabledReason: "Ask first", run: () => undefined });

    const results = buildPaletteResults({ commands: registry.all(), panels: [], quickOpen: [], query: "git" });

    expect(results.actions[0].id).toBe("git.init");
    expect(results.actions[0].disabledReason).toBe("Ask first");
  });

  test("distinguishes panels and quick-open objects", () => {
    const quickOpen = quickOpenFromObjects({
      notes: [{ id: "n1", title: "Method note" }],
      sources: [],
      tasks: [],
      claims: [],
      citations: [],
    });

    const results = buildPaletteResults({
      commands: [],
      panels: [{ panelId: "explorer", title: "Explorer" }],
      quickOpen,
      query: "method",
    });

    expect(results.quickOpen[0].type).toBe("note");
    expect(results.panels).toHaveLength(0);
  });
});
