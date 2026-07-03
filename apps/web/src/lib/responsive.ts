import { useEffect, useState } from "react";

/**
 * Adaptive surface detection + capability matrix (branch 03-09).
 *
 * The desktop FlexLayout workbench is the primary product and MUST stay unchanged;
 * this module only decides WHEN a phone/tablet surface is eligible and WHICH flows it
 * may render. It never mutates desktop state — consumers branch on the result.
 *
 * Breakpoint / pointer policy (spec-silent thresholds decided by this branch, see
 * `.agents/learned-rules.md`): a resized desktop window with a fine mouse pointer must
 * NOT get mobile chrome; only touch-primary (coarse / no-hover) devices do.
 *   - desktop: `(pointer: fine)` OR viewport width >= 1280px
 *   - tablet : NOT desktop AND coarse/no-hover pointer AND width 640-1279px
 *   - phone  : NOT desktop AND coarse/no-hover pointer AND width < 640px
 *   - any other combination falls back to desktop.
 */
export type Surface = "phone" | "tablet" | "desktop";

const DESKTOP_MIN_WIDTH = 1280;
const PHONE_MAX_WIDTH = 640; // exclusive upper bound for phones

function matchesMedia(query: string): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia(query).matches;
}

function viewportWidth(): number {
  return typeof window === "undefined" ? DESKTOP_MIN_WIDTH : window.innerWidth;
}

export function getSurface(): Surface {
  const width = viewportWidth();
  // A fine pointer (mouse/trackpad) or a wide viewport is always the desktop workbench.
  if (matchesMedia("(pointer: fine)") || width >= DESKTOP_MIN_WIDTH) return "desktop";
  // Below desktop width AND touch-primary: split by width. Anything without a
  // coarse/no-hover pointer (e.g. a narrow window on a desktop) stays desktop.
  const touchPrimary = matchesMedia("(pointer: coarse), (hover: none)");
  if (!touchPrimary) return "desktop";
  return width < PHONE_MAX_WIDTH ? "phone" : "tablet";
}

/** Subscribes to pointer/hover media + viewport resize and returns the live surface. */
export function useSurface(): Surface {
  const [surface, setSurface] = useState<Surface>(() => getSurface());
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const update = () => setSurface(getSurface());
    const queries = ["(pointer: fine)", "(pointer: coarse)", "(hover: none)"].map((query) => window.matchMedia(query));
    queries.forEach((mql) => mql.addEventListener("change", update));
    window.addEventListener("resize", update);
    update();
    return () => {
      queries.forEach((mql) => mql.removeEventListener("change", update));
      window.removeEventListener("resize", update);
    };
  }, []);
  return surface;
}

/**
 * The 6 primary companion flows plus the desktop-only set. The primary flows reuse the
 * existing desktop panel contracts verbatim; the desktop-only set renders an
 * unsupported-on-this-surface state if ever reached from mobile chrome.
 */
export type CapabilityFlow =
  | "read"
  | "review"
  | "annotate"
  | "notes"
  | "tasks"
  | "chat"
  // desktop-only
  | "orchestration"
  | "terminal"
  | "heavy-docx"
  | "deep-settings"
  | "experiments"
  | "autopilot"
  | "explorer"
  | "source-discovery"
  | "git"
  | "browser"
  | "citation-evidence"
  | "exports"
  | "logs"
  | "problems"
  | "writing"
  | "agent-runs";

export type SupportState = "supported" | "simplified" | "unsupported";

export const PRIMARY_FLOWS: readonly CapabilityFlow[] = ["read", "review", "annotate", "notes", "tasks", "chat"] as const;

const PRIMARY_FLOW_SET = new Set<CapabilityFlow>(PRIMARY_FLOWS);

/**
 * Support state for a flow on a surface.
 *   - desktop keeps its existing FlexLayout access to everything → always `supported`.
 *   - the 6 primary flows: `supported` on tablet (room for the full panel), `simplified`
 *     on phone (same contract, single-column touch chrome).
 *   - every desktop-only flow: `unsupported` on phone AND tablet — mobile/tablet is a
 *     focused companion surface, not a shrunk desktop (guide Non-Goals, HL-UX-31/34).
 */
export function capabilityFor(flow: CapabilityFlow, surface: Surface): SupportState {
  if (surface === "desktop") return "supported";
  if (PRIMARY_FLOW_SET.has(flow)) return surface === "tablet" ? "supported" : "simplified";
  return "unsupported";
}
