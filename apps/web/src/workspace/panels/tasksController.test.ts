import { describe, expect, test } from "bun:test";
import type { TaskRecord } from "../../lib/api";
import { KANBAN_COLUMNS, activeTasks, collectTags, draftTasks, filterByTag, groupByColumn } from "./tasksController";

const task = (over: Partial<TaskRecord>): TaskRecord => ({ id: "t", title: "t", column: "to_do", ...over });

describe("kanban columns", () => {
  test("exposes the four normative columns in order", () => {
    expect(KANBAN_COLUMNS.map((c) => c.label)).toEqual(["To Do", "In Progress", "Review", "Done"]);
    expect(KANBAN_COLUMNS.map((c) => c.id)).toEqual(["to_do", "in_progress", "review", "done"]);
  });
});

describe("tag filter (HL-UX-02)", () => {
  const tasks = [
    task({ id: "a", title: "Check arXiv 1706.03762 metadata", tags: ["metadata"] }),
    task({ id: "b", title: "Draft methods section", tags: ["writing"] }),
  ];
  test("keeps matching, hides non-matching", () => {
    const filtered = filterByTag(tasks, "metadata");
    expect(filtered.map((t) => t.id)).toEqual(["a"]);
  });
  test("no filter returns all", () => {
    expect(filterByTag(tasks, null)).toHaveLength(2);
  });
  test("collects the tag universe", () => {
    expect(collectTags(tasks)).toEqual(["metadata", "writing"]);
  });
});

describe("lifecycle split (HL-UX-06/07)", () => {
  const tasks = [task({ id: "a" }), task({ id: "d", lifecycle_state: "draft" }), task({ id: "x", lifecycle_state: "dismissed" })];
  test("active excludes drafts and dismissed", () => {
    expect(activeTasks(tasks).map((t) => t.id)).toEqual(["a"]);
  });
  test("drafts collects only draft lifecycle", () => {
    expect(draftTasks(tasks).map((t) => t.id)).toEqual(["d"]);
  });
});

describe("groupByColumn", () => {
  test("buckets tasks by column with to_do default", () => {
    const groups = groupByColumn([task({ id: "a", column: "review" }), task({ id: "b", column: "" })]);
    expect(groups.review.map((t) => t.id)).toEqual(["a"]);
    expect(groups.to_do.map((t) => t.id)).toEqual(["b"]);
  });
});
