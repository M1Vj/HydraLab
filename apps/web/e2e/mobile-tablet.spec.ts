/**
 * Adaptive phone/tablet surface E2E (branch 03-09).
 *
 * Startup (same as workbench.spec.ts):
 * 1. Backend: `HYDRA_HOME=/path/to/project uvicorn hydra.app:app --host 127.0.0.1 --port 8765`
 * 2. Frontend: `bun --cwd apps/web run dev`
 * 3. Run: `PLAYWRIGHT_BASE_URL=http://127.0.0.1:5173 bun --cwd apps/web run test:e2e`
 *
 * Every test skips when the frontend/backend dev servers are absent (same guard as
 * workbench.spec.ts), so this spec is safe to add even though no server runs during the
 * headless build. Device presets (iPhone/iPad) are used so the `pointer:coarse` /
 * `hover:none` detection in `src/lib/responsive.ts` actually triggers under test.
 */
import { devices, expect, test } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173";

// Playwright forbids a full device preset inside test.describe() because the preset's
// `defaultBrowserType` forces a new worker. Strip it: the touch/viewport/isMobile fields
// (which drive `pointer:coarse` / `hover:none` emulation in Chromium) are what we need.
function touchPreset(name: "iPhone 13" | "iPad (gen 7)") {
  const { defaultBrowserType: _ignored, ...rest } = devices[name];
  return rest;
}
const PHONE = touchPreset("iPhone 13");
const TABLET = touchPreset("iPad (gen 7)");

async function serversUp(page: import("@playwright/test").Page): Promise<boolean> {
  const frontend = await fetch(baseURL).then((response) => response.ok).catch(() => false);
  test.skip(!frontend, "HydraLab frontend dev server is not running");
  const backend = await fetch(`${baseURL}/api/health`).then((response) => response.ok).catch(() => false);
  test.skip(!backend, "HydraLab backend is not running behind the Vite proxy");
  await page.goto(baseURL);
  return frontend && backend;
}

/** Opens the default project and enables the Phase-3 mobile flag through the real Settings UI. */
async function openProjectAndEnableMobileFlag(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: "Open existing folder" }).click();
  await expect(page.getByRole("navigation", { name: "Activity Bar" })).toBeVisible();
  await page.getByRole("button", { name: "Settings" }).click();
  const toggle = page.getByLabel("Adaptive phone/tablet surface (Phase 3)");
  if (!(await toggle.isChecked())) await toggle.check();
}

test.describe("phone surface", () => {
  test.use(PHONE);

  test("flag OFF keeps the desktop workbench even at phone width", async ({ page }) => {
    await serversUp(page);
    await page.getByRole("button", { name: "Open existing folder" }).click();
    // Flag defaults OFF → desktop FlexLayout path renders regardless of the coarse pointer.
    await expect(page.getByRole("navigation", { name: "Activity Bar" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Mobile navigation" })).toHaveCount(0);
  });

  test("flag ON exposes exactly the six primary flows and no workbench dock", async ({ page }) => {
    await serversUp(page);
    await openProjectAndEnableMobileFlag(page);

    const nav = page.getByRole("navigation", { name: "Mobile navigation" });
    await expect(nav).toBeVisible();
    for (const label of ["Read", "Review", "Annotate", "Notes", "Tasks", "Chat"]) {
      await expect(nav.getByRole("button", { name: label })).toBeVisible();
    }
    // No desktop-only primary flows and no FlexLayout dock on the mobile surface.
    await expect(nav.getByRole("button", { name: "Console" })).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: "Activity Bar" })).toHaveCount(0);
    await expect(page.locator(".flexlayout__tabset")).toHaveCount(0);
  });

  test("primary nav actions meet the 44px touch-target minimum", async ({ page }) => {
    await serversUp(page);
    await openProjectAndEnableMobileFlag(page);
    const tab = page.getByRole("navigation", { name: "Mobile navigation" }).getByRole("button", { name: "Chat" });
    const box = await tab.boundingBox();
    expect(box, "nav button geometry").not.toBeNull();
    if (box) {
      expect(box.width).toBeGreaterThanOrEqual(44);
      expect(box.height).toBeGreaterThanOrEqual(44);
    }
  });

  test("reduced motion: switching tabs settles without a long transition", async ({ page }) => {
    await serversUp(page);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await openProjectAndEnableMobileFlag(page);
    const nav = page.getByRole("navigation", { name: "Mobile navigation" });
    await nav.getByRole("button", { name: "Notes" }).click();
    await nav.getByRole("button", { name: "Tasks" }).click();
    await expect(nav.getByRole("button", { name: "Tasks" })).toHaveAttribute("aria-current", "page");
    const transition = await nav
      .getByRole("button", { name: "Tasks" })
      .evaluate((el) => getComputedStyle(el).transitionDuration);
    // Global reduced-motion rule forces transitions off.
    expect(["0s", "0ms", ""]).toContain(transition);
  });
});

test.describe("tablet surface", () => {
  test.use(TABLET);

  test("flag ON renders the mobile companion surface on a tablet", async ({ page }) => {
    await serversUp(page);
    await openProjectAndEnableMobileFlag(page);
    await expect(page.getByRole("navigation", { name: "Mobile navigation" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Activity Bar" })).toHaveCount(0);
  });
});

test.describe("desktop surface", () => {
  test("flag ON keeps the FlexLayout workbench (fine pointer overrides)", async ({ page }) => {
    await serversUp(page);
    await openProjectAndEnableMobileFlag(page);
    // A fine-pointer desktop must NOT get mobile chrome even with the flag on.
    await expect(page.getByRole("navigation", { name: "Activity Bar" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Mobile navigation" })).toHaveCount(0);
  });
});

test.describe("performance smoke (HL-UX-39)", () => {
  test.use(TABLET);

  test("large PDF open + scroll + note keystroke targets", async ({ page }) => {
    await serversUp(page);
    // Structural perf-smoke: correct targets/measurement, but no >=200-page PDF fixture
    // exists in this repo (only backend/tests/fixtures/ingestion/sample-paper.pdf). Do
    // not fabricate a large binary — skip until a suitable fixture is added.
    test.skip(true, "no >=200-page PDF fixture available in this repo; add one under backend/tests/fixtures to un-skip");

    const OPEN_BUDGET_MS = 1500; // first visible page < 1500ms
    const FREEZE_BUDGET_MS = 50; // no main-thread freeze > 50ms while scrolling
    const KEYSTROKE_BUDGET_MS = 50; // note keystroke-to-render < 50ms
    expect(OPEN_BUDGET_MS).toBe(1500);
    expect(FREEZE_BUDGET_MS).toBe(50);
    expect(KEYSTROKE_BUDGET_MS).toBe(50);
  });
});
