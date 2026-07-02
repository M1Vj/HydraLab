import { describe, expect, test } from "bun:test";
import { moveTaskOptimistically } from "./TasksPanel";

describe("kanban optimistic move", () => {
  test("moves a task locally while preserving rollback source", () => {
    const before = [{ id: "task-1", title: "Read paper", column: "to_do" }];
    const after = moveTaskOptimistically(before, "task-1", "done");

    expect(after[0].column).toBe("done");
    expect(before[0].column).toBe("to_do");
  });
});
