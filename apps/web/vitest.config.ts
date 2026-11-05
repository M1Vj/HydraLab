// HydraLab web unit-test configuration (hermetic dual-runtime).
//
// Goal: `npm test` must pass on merge-gate runners that have Node + npm but
// NO bun binary, while `bun test` keeps working unchanged for local dev.
//
// Strategy (no downgrade, no mocks of product code):
// - Unit tests stay exactly as written (`import ... from "bun:test"`).
// - Under bun, the `test` script runs `bun test src` (native).
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
// - `include` covers `src/**/*.{test,spec}.{ts,tsx,js,jsx,mts,cts}` so every
//   test `bun test src` would discover is also discovered here; Playwright e2e
//   specs in `e2e/**` stay under `test:e2e` (`playwright test`) and never run
//   here. Equivalence is verified by `node scripts/dual-run.mjs
//   test:equivalence`, which logs BRANCH=bun vs BRANCH=npm-vitest and compares.
// - Fail-fast guards: `retry: 0` (no silent retries of flaky tests);
//   reporters stay `default` so failures print full diffs for the gate.
// - Lockfile: pdfjs-dist 6.2.108 + vitest ^3.2.4 require a regenerated
//   bun.lock / package-lock.json. CI runs `verify:lockfile` (see
//   scripts/dual-run.mjs); if the lockfile is absent the check fails unless
//   HYDRA_ALLOW_MISSING_LOCKFILE=1, in which case it prints a clear SKIP
//   reason instead of silently passing.
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
        "import { vi, describe, test, it, expect, beforeEach, afterEach, beforeAll, afterAll } from 'vitest';",
        "export { vi, describe, test, it, expect, beforeEach, afterEach, beforeAll, afterAll };",
        "export { vi as jest };",
        "export const spyOn = vi.spyOn;",
        "export function mock(fn) { return typeof fn === 'function' ? vi.fn(fn) : vi.fn(); }",
        "mock.fn = (impl) => vi.fn(impl);",
        "mock.spyOn = (...args) => vi.spyOn(...args);",
        "mock.module = (path, factory) => vi.mock(path, factory);",
        "mock.restore = () => vi.restoreAllMocks();",
        "mock.clearAllMocks = () => vi.clearAllMocks();",
        "mock.resetAllMocks = () => vi.resetAllMocks();",
        "mock.useFakeTimers = (...args) => vi.useFakeTimers(...args);",
        "mock.useRealTimers = (...args) => vi.useRealTimers(...args);",
        "mock.stubGlobal = (...args) => vi.stubGlobal(...args);",
        "mock.unstubAllGlobals = () => vi.unstubAllGlobals();",
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
    include: ["src/**/*.{test,spec}.{ts,tsx,js,jsx,mts,cts}"],
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
    reporters: ["default"],
    // Fail-fast: never silently retry; a failure is a failure.
    retry: 0,
  },
});