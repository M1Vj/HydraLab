// HydraLab chrome-extension unit-test configuration (hermetic dual-runtime).
//
// Mirrors apps/web/vitest.config.ts so the root `npm test` fallback covers
// BOTH suites: `bun test apps/web/src apps/chrome-extension/src` under bun,
// and web vitest + chrome-extension vitest under npm. Without this file the
// npm fallback would silently drop chrome-extension coverage (anti-downgrade
// violation). See scripts/dual-run.mjs `test` branch for the exact commands
// and BRANCH=bun / BRANCH=npm-vitest logging.
//
// - Tests stay as written (`from "bun:test"`); the plugin below delegates to
//   the REAL vitest implementation (no product stubs).
// - `environment: "node"`, no network/secrets; e2e stays out (`e2e/**`
//   excluded).
// - `include` matches everything `bun test src` discovers:
//   `src/**/*.{test,spec}.{ts,tsx,js,jsx,mts,cts}`.
// - Fail-fast: `retry: 0`.
//
// Security: no network egress, no secrets, only transforms checked-in tests.
import { defineConfig } from "vitest/config";
import type { Plugin } from "vite";

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
    retry: 0,
  },
});