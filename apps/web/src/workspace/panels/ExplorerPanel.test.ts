import { describe, expect, test } from "bun:test";
import { flattenRawTree } from "./ExplorerPanel";
import type { ProjectTreeNode } from "../../lib/api";

describe("explorer virtualization data prep", () => {
  test("flattens 5,000 raw nodes under the 100ms smoke target", () => {
    const nodes: ProjectTreeNode[] = Array.from({ length: 5000 }, (_, index) => ({
      id: `knowledge/note-${index}.md`,
      path: `knowledge/note-${index}.md`,
      name: `note-${index}.md`,
      type: "file",
      parent: "knowledge",
      depth: 1,
      size: 12,
      modified_at: 0,
      index_status: "indexed",
    }));

    const started = performance.now();
    const rows = flattenRawTree(nodes);
    const elapsed = performance.now() - started;

    expect(rows).toHaveLength(5000);
    expect(elapsed).toBeLessThan(100);
  });
});
