import { afterEach, describe, expect, test } from "bun:test";
import { capabilityFor, getSurface, PRIMARY_FLOWS, type CapabilityFlow, type Surface } from "./responsive";

type Pointer = "fine" | "coarse" | "none";

function mockViewport(opts: { width: number; pointer: Pointer }) {
  const fine = opts.pointer === "fine";
  const coarse = opts.pointer === "coarse";
  const noHover = opts.pointer !== "fine";
  const matches = (query: string): boolean => {
    if (query.includes("pointer: fine")) return fine;
    if (query.includes("pointer: coarse") && query.includes("hover: none")) return coarse || noHover;
    if (query.includes("pointer: coarse")) return coarse;
    if (query.includes("hover: none")) return noHover;
    return false;
  };
  (globalThis as unknown as { window: unknown }).window = {
    innerWidth: opts.width,
    matchMedia: (query: string) => ({ matches: matches(query), addEventListener() {}, removeEventListener() {} }),
    addEventListener() {},
    removeEventListener() {},
  };
}

afterEach(() => {
  delete (globalThis as unknown as { window?: unknown }).window;
});

describe("getSurface", () => {
  test("fine pointer on a wide viewport is desktop", () => {
    mockViewport({ width: 1440, pointer: "fine" });
    expect(getSurface()).toBe("desktop");
  });

  test("fine pointer on a narrow viewport stays desktop (resized window, not a phone)", () => {
    mockViewport({ width: 480, pointer: "fine" });
    expect(getSurface()).toBe("desktop");
  });

  test("coarse pointer under 640px is phone", () => {
    mockViewport({ width: 375, pointer: "coarse" });
    expect(getSurface()).toBe("phone");
  });

  test("no-hover pointer under 640px is phone", () => {
    mockViewport({ width: 414, pointer: "none" });
    expect(getSurface()).toBe("phone");
  });

  test("coarse pointer 640-1279px is tablet", () => {
    mockViewport({ width: 834, pointer: "coarse" });
    expect(getSurface()).toBe("tablet");
  });

  test("coarse pointer at 640px boundary is tablet", () => {
    mockViewport({ width: 640, pointer: "coarse" });
    expect(getSurface()).toBe("tablet");
  });

  test("coarse pointer at/above 1280px is desktop", () => {
    mockViewport({ width: 1280, pointer: "coarse" });
    expect(getSurface()).toBe("desktop");
  });

  test("no window (SSR/non-DOM) falls back to desktop", () => {
    delete (globalThis as unknown as { window?: unknown }).window;
    expect(getSurface()).toBe("desktop");
  });
});

describe("capabilityFor", () => {
  const desktopOnly: CapabilityFlow[] = [
    "orchestration",
    "terminal",
    "heavy-docx",
    "deep-settings",
    "experiments",
    "autopilot",
    "explorer",
    "source-discovery",
    "git",
    "browser",
    "citation-evidence",
    "exports",
    "logs",
    "problems",
    "writing",
    "agent-runs",
  ];

  test("every flow is supported on desktop", () => {
    for (const flow of [...PRIMARY_FLOWS, ...desktopOnly]) {
      expect(capabilityFor(flow as CapabilityFlow, "desktop")).toBe("supported");
    }
  });

  test("primary flows are supported on tablet and simplified on phone", () => {
    for (const flow of PRIMARY_FLOWS) {
      expect(capabilityFor(flow, "tablet")).toBe("supported");
      expect(capabilityFor(flow, "phone")).toBe("simplified");
    }
  });

  test("desktop-only flows are unsupported on phone and tablet", () => {
    for (const flow of desktopOnly) {
      for (const surface of ["phone", "tablet"] as Surface[]) {
        expect(capabilityFor(flow, surface)).toBe("unsupported");
      }
    }
  });
});
