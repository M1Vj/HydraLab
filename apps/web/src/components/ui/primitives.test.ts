import { describe, expect, it } from "bun:test";

import { nextTabIndex } from "./primitives";

describe("nextTabIndex (tablist keyboard navigation)", () => {
  it("moves right/down to the next tab", () => {
    expect(nextTabIndex(0, "ArrowRight", 4)).toBe(1);
    expect(nextTabIndex(1, "ArrowDown", 4)).toBe(2);
  });

  it("moves left/up to the previous tab", () => {
    expect(nextTabIndex(2, "ArrowLeft", 4)).toBe(1);
    expect(nextTabIndex(2, "ArrowUp", 4)).toBe(1);
  });

  it("wraps around both ends", () => {
    expect(nextTabIndex(3, "ArrowRight", 4)).toBe(0);
    expect(nextTabIndex(0, "ArrowLeft", 4)).toBe(3);
  });

  it("jumps to first and last with Home/End", () => {
    expect(nextTabIndex(2, "Home", 4)).toBe(0);
    expect(nextTabIndex(1, "End", 4)).toBe(3);
  });

  it("ignores non-navigation keys", () => {
    expect(nextTabIndex(1, "Enter", 4)).toBeNull();
    expect(nextTabIndex(1, "a", 4)).toBeNull();
  });

  it("is safe with an empty tablist", () => {
    expect(nextTabIndex(-1, "ArrowRight", 0)).toBeNull();
  });

  it("advances to the first tab from an unknown current selection", () => {
    expect(nextTabIndex(-1, "ArrowRight", 4)).toBe(0);
  });
});
