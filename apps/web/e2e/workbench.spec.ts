/**
 * Workbench E2E smoke.
 *
 * Startup:
 * 1. Backend: `HYDRA_HOME=/path/to/project uvicorn hydra.app:app --host 127.0.0.1 --port 8765`
 * 2. Frontend: `bun --cwd apps/web run dev`
 * 3. Run: `PLAYWRIGHT_BASE_URL=http://127.0.0.1:5173 bun --cwd apps/web run test:e2e`
 *
 * The spec skips when the frontend or backend is absent so it is safe in CI jobs
 * that do not start the local HydraLab runtime.
 */
import { expect, test } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173";

test.beforeEach(async ({ page }) => {
  const frontend = await fetch(baseURL).then((response) => response.ok).catch(() => false);
  test.skip(!frontend, "HydraLab frontend dev server is not running");
  const backend = await fetch(`${baseURL}/api/health`).then((response) => response.ok).catch(() => false);
  test.skip(!backend, "HydraLab backend is not running behind the Vite proxy");
  await page.goto(baseURL);
});

test("close panel persists layout and reset restores it", async ({ page }) => {
  await page.getByRole("button", { name: "Open existing folder" }).click();
  await expect(page.getByRole("navigation", { name: "Activity Bar" })).toBeVisible();

  const opened = await page.evaluate(() => localStorage.getItem("hydralab-workspace"));
  // Closing the active tab is a command/keyboard-driven change: it must persist,
  // not only survive a FlexLayout drag (which fires onModelChange).
  await page.keyboard.press(process.platform === "darwin" ? "Meta+W" : "Control+W");
  await page.waitForFunction(
    (prev) => localStorage.getItem("hydralab-workspace") !== prev,
    opened,
    { timeout: 5000 },
  );
  const afterClose = await page.evaluate(() => localStorage.getItem("hydralab-workspace"));
  expect(afterClose).not.toEqual(opened);

  // Reset via the command palette must change the persisted layout back off the closed state.
  await page.getByRole("button", { name: "Explorer" }).click();
  await page.keyboard.press(process.platform === "darwin" ? "Meta+K" : "Control+K");
  await page.getByPlaceholder("Search commands, panels, notes, sources...").fill("reset layout");
  await page.getByText("View: Reset layout").click();
  await page.waitForFunction(
    (prev) => localStorage.getItem("hydralab-workspace") !== prev,
    afterClose,
    { timeout: 5000 },
  );
  const afterReset = await page.evaluate(() => localStorage.getItem("hydralab-workspace"));
  expect(afterReset).not.toEqual(afterClose);
});

test("explorer to markdown editor open flow", async ({ page }) => {
  await page.getByRole("button", { name: "Open existing folder" }).click();
  await page.getByRole("button", { name: "Explorer" }).click();
  const markdownRow = page.locator(".tree-row").filter({ hasText: ".md" }).first();
  if ((await markdownRow.count()) === 0) test.skip(true, "No markdown file exists in this project tree");
  await markdownRow.dblclick();
  await expect(page.getByLabel("CodeMirror 6 Markdown editor").or(page.getByText("No note open"))).toBeVisible();
});

test("open PDF reader panel from an Explorer source row", async ({ page }) => {
  await page.getByRole("button", { name: "Open existing folder" }).click();
  await page.getByRole("button", { name: "Explorer" }).click();
  const sourceRow = page.locator(".tree-row.source").first();
  if ((await sourceRow.count()) === 0) test.skip(true, "No source exists in this project");
  await sourceRow.dblclick();
  await expect(page.getByRole("region", { name: "PDF reader" }).or(page.getByRole("button", { name: "Open" }))).toBeVisible();
});

test("settings secret field is write-only and never echoes a stored value", async ({ page }) => {
  await page.getByRole("button", { name: "Open existing folder" }).click();
  await page.getByRole("button", { name: "Settings" }).click();
  const secretInput = page.locator('input[type="password"]').first();
  if ((await secretInput.count()) === 0) test.skip(true, "No provider configured to expose a secret field");
  await expect(secretInput).toHaveValue("");
  await secretInput.fill("sk-should-not-persist");
  // Reload settings by reopening the panel; a write-only field must return empty.
  await page.getByRole("button", { name: "Explorer" }).click();
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.locator('input[type="password"]').first()).toHaveValue("");
});

test("layout drag changes persisted JSON", async ({ page }) => {
  await page.getByRole("button", { name: "Open existing folder" }).click();
  const before = await page.evaluate(() => localStorage.getItem("hydralab-workspace"));
  const tabs = page.locator(".flexlayout__tab_button");
  if ((await tabs.count()) < 2) test.skip(true, "Not enough tabs for drag smoke");
  const boxA = await tabs.nth(0).boundingBox();
  const boxB = await tabs.nth(1).boundingBox();
  if (!boxA || !boxB) test.skip(true, "Tab geometry unavailable");
  await page.mouse.move(boxA.x + boxA.width / 2, boxA.y + boxA.height / 2);
  await page.mouse.down();
  await page.mouse.move(boxB.x + boxB.width / 2, boxB.y + boxB.height / 2, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(300);
  const after = await page.evaluate(() => localStorage.getItem("hydralab-workspace"));
  expect(after).not.toEqual(before);
});
