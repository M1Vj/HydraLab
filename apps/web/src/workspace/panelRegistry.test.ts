import { describe, expect, test } from "bun:test";
import { panelTitle } from "./panelRegistry";

describe("panelTitle", () => {
  test("derives the hostname for a valid browser url", () => {
    expect(panelTitle("browser", { url: "https://arxiv.org/abs/1706.03762" })).toBe("arxiv.org");
  });

  test("does not throw on a malformed browser url (would white-screen the shell)", () => {
    expect(() => panelTitle("browser", { url: "not a url" })).not.toThrow();
    expect(panelTitle("browser", { url: "not a url" })).toBe("not a url");
  });

  test("falls back to the chrome title when the browser url is empty", () => {
    expect(panelTitle("browser", { url: "" })).toBe("Browser");
  });

  test("uses the configured title for editor/pdf tabs", () => {
    expect(panelTitle("markdown-editor", { title: "intro.md" })).toBe("intro.md");
    expect(panelTitle("pdf-reader", { title: "paper.pdf" })).toBe("paper.pdf");
  });

  test("defaults to the panel chrome title", () => {
    expect(panelTitle("tasks")).toBe("Tasks");
  });
});
