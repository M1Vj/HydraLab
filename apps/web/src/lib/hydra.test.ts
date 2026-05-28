import { describe, expect, test } from "bun:test";

import { groupTasksByColumn, sourceLabel, statusCopy } from "./hydra";

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
});
