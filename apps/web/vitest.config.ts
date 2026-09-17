// HydraLab web unit-test configuration (hermetic dual-runtime).
//
// Goal: `npm test` must pass on merge-gate runners that have Node + npm but
// NO bun binary, while `bun test` keeps working unchanged for local dev.
//
// Strategy (no downgrade, no mocks of product code):
// - Unit tests stay exactly as written (`import ... from "bun:test"`).
// - Under bun, `apps/web/package.json` `test` runs `bun test src` (native).
// - Under npm (bun missing), it runs `vitest run` with this config.
// - The `bun-test-compat` plugin below resolves the `bun:test` specifier to a
//   thin virtual module that re-exports the REAL vitest implementation
//   (`describe/test/it/expect/beforeEach/afterEach/...` + `vi`). `mock(fn)`
//   delegates to `vi.fn(fn)` so call-count assertions
//   (`toHaveBeenCalledTimes/With`) keep verifying real behavior; no product
//   logic is stubbed, skipped, or weakened.
// - `environment: "node"` because unit tests are pure logic and mock `window`
//   via `globalThis` themselves (see `src/lib/responsive.test.ts`); no DOM,
//   browser, or network is required, keeping the check hermetic.
// - `include` is limited to `src/**/*.test.ts`; Playwright e2e specs in
//   `e2e/**` stay under `test:e2e` (`playwright test`) and never run here.
// - Fail-fast guards: `retry: 0` (no silent retries of flaky tests);
//   reporters stay `default` so failures print full diffs for the gate.
//
// Security: this config performs no network egress, reads no secrets, and
// does not execute repository-provided workflow code; it only transforms and
// runs the checked-in unit tests.
import { defineConfig } from "vitest/config";
import type { Plugin } from "vite";

// Resolve `bun:test` imports to real vitest primitives when running under npm.
// Bun itself resolves `bun:test` natively, so this plugin is a no-op there.
function bunTestCompat(): Plugin {
  return {
    name: "bun-test-compat",
    enforce: "pre",
    resolveId(id) {
      if (id === "bun:test") return "\0virtual:bun-test";
      return null;
    },
    load(id) {
      if (id !== "\0virtual:bun-test") return null;
      return [
        "export * from 'vitest';",
        "import { vi } from 'vitest';",
        "export { vi };",
        "export const jest = vi;",
        "export const spyOn = (...args) => vi.spyOn(...args);",
        "export function mock(fn) { return typeof fn === 'function' ? vi.fn(fn) : vi.fn(); }",
        "mock.restore = () => vi.restoreAllMocks();",
        "mock.clearAllMocks = () => vi.clearAllMocks();",
        "export default { mock, spyOn, jest: vi };",
        "",
      ].join("\n");
    },
  };
}

export default defineConfig({
  plugins: [bunTestCompat()],
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    exclude: ["e2e/**", "node_modules/**"],
    reporters: ["default"],
    // Fail-fast: never silently retry; a failure is a failure.
    retry: 0,
  },
});