#!/usr/bin/env node
/**
 * scripts/ensure-bun.mjs — HydraLab Bun preflight + command dispatcher (hardened).
 *
 * Purpose:
 *   Verify a pinned Bun toolchain exists, then delegate to the REAL Bun-based
 *   build/test/typecheck behavior exactly (genuine toolchain, full fidelity).
 *   Designed for runners provisioned via `oven-sh/setup-bun` in CI (see
 *   `.github/workflows/ci.yml`, pinned to the same version below).
 *
 * Real commands preserved (identical to the pre-change package.json intent):
 *   dev       -> bun run --filter @hydra/web dev
 *   build     -> bun run --filter @hydra/web build && bun run --filter @hydra/chrome-extension build
 *                (executed as two sequential fail-fast steps)
 *   test      -> bun test apps/web/src apps/chrome-extension/src
 *   test:e2e  -> bun run --filter @hydra/web test:e2e
 *   typecheck -> bun run --filter @hydra/web typecheck && bun run --filter @hydra/chrome-extension typecheck
 *                (executed as two sequential fail-fast steps)
 *   lint      -> semantically identical to `bun run typecheck` (the two
 *                typecheck steps above). Expanded explicitly to avoid
 *                recursing through this wrapper: package.json `lint`
 *                delegates here, so running `bun run typecheck` from inside
 *                would re-enter this dispatcher instead of the workspaces.
 *
 * Security hardening (addresses audit blockers — do not regress):
 *   - NO network bootstrap: no `curl|bash`, no `https://bun.sh/install`,
 *     no `npm install -g`. If `bun` is missing the dispatcher fails closed
 *     with an actionable message (install the pinned version via
 *     `oven-sh/setup-bun@v2` with `bun-version: <pinned>`). Runners without
 *     Bun can only be handled at the workflow level (explicit `if:` /
 *     `paths-ignore` with a recorded reason), never by this script exiting 0.
 *   - NO skip-to-pass gates: HYDRA_SKIP_UI_BUILD / HYDRA_SKIP_UI_TEST /
 *     HYDRA_SKIP_TYPECHECK / HYDRA_SKIP_FRONTEND are NOT honored. Setting
 *     them does not skip work. Required CI steps additionally assert these
 *     variables are unset so verification cannot be vacuously green.
 *   - NO env-overridable installer spec: the pinned version below is the
 *     single source of truth (mirrors `packageManager` in package.json).
 *     A `BUN_VERSION` env var, if present, is strictly validated
 *     (`/^\d+\.\d+\.\d+$/`) and must equal the pinned version; any other
 *     value fails closed. It is never interpolated into a shell string —
 *     all subprocesses use argument arrays with no shell.
 *   - NO global mutation without consent: read-only Bun resolution only
 *     (`bun` on PATH, `$HOME/.bun/bin/bun`, `node_modules/.bin/bun`). No
 *     writes to `~/.bun`, no PATH rewriting, no global installs. Version
 *     drift fails closed unless explicitly consented with
 *     `HYDRA_ALLOW_BUN_DRIFT=1`.
 *   - NO shell-string execution of toolchain commands: every step runs via
 *     `spawnSync(bunBin, argsArray)` with `shell: false`. Fail-fast: any
 *     non-zero status aborts remaining steps and exits non-zero.
 *
 * Docs/security invariant: no secrets handling, no SECURITY.md / docs flow
 * changes, no capability deletions — preflight plus faithful delegation only.
 */

import process from "node:process";
import path from "node:path";
import os from "node:os";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

/** Single source of truth for the required Bun version. Mirrors package.json `packageManager`. Not overridable. */
export const PINNED_BUN_VERSION = "1.3.11";

const STRICT_VERSION_RE = /^\d+\.\d+\.\d+$/;

export const ALLOWED_COMMANDS = Object.freeze([
  "dev",
  "build",
  "test",
  "test:e2e",
  "typecheck",
  "lint",
  "--ensure",
]);

export function log(msg) {
  console.log(`[ensure-bun] ${msg}`);
}

export function fail(msg, code = 1) {
  console.error(`[ensure-bun] ERROR: ${msg}`);
  process.exit(code);
}

/**
 * Strictly validate an optional BUN_VERSION env override.
 * Returns null when unset. Throws when malformed or when it disagrees with
 * the pinned version — the env var can never retarget the toolchain.
 */
export function checkBunVersionEnv(env = process.env) {
  const raw = env?.BUN_VERSION;
  if (raw === undefined || raw === null || String(raw).trim() === "") return null;
  const value = String(raw).trim();
  if (!STRICT_VERSION_RE.test(value)) {
    throw new Error(
      `BUN_VERSION=${JSON.stringify(value)} is not a strict X.Y.Z version; expected exactly ${PINNED_BUN_VERSION}.`,
    );
  }
  if (value !== PINNED_BUN_VERSION) {
    throw new Error(
      `BUN_VERSION=${value} disagrees with pinned bun@${PINNED_BUN_VERSION}; refusing to retarget the toolchain.`,
    );
  }
  return value;
}

/** Read-only Bun candidates for a platform. No installs, no writes. */
export function bunCandidates({ platform = process.platform, homedir = os.homedir(), cwd = process.cwd() } = {}) {
  const exe = platform === "win32" ? "bun.exe" : "bun";
  const cands = ["bun"];
  if (homedir) cands.push(path.join(homedir, ".bun", "bin", exe));
  // npm/bun workspaces expose a local shim; probed read-only (never installed here).
  cands.push(path.join(cwd, "node_modules", ".bin", exe));
  return cands;
}

/**
 * Resolve an existing Bun binary (read-only probe with `--version`).
 * Returns `{ bin, version }` or null when no candidate responds successfully.
 */
export function resolveBun(
  { platform = process.platform, homedir = os.homedir(), cwd = process.cwd(), spawn = spawnSync } = {},
) {
  for (const cand of bunCandidates({ platform, homedir, cwd })) {
    try {
      const r = spawn(cand, ["--version"], { encoding: "utf8", timeout: 15000, shell: false });
      const out = String(r?.stdout ?? "").trim();
      if (r?.status === 0 && STRICT_VERSION_RE.test(out.split("-")[0].split("+")[0]) && out.length > 0) {
        return { bin: cand, version: out };
      }
    } catch {
      // ignore and try next candidate
    }
  }
  return null;
}

/**
 * Fail-closed preflight: require Bun at the pinned version.
 * Version drift fails unless HYDRA_ALLOW_BUN_DRIFT=1 (explicit consent).
 */
export function ensureBun({ env = process.env, resolve = resolveBun } = {}) {
  checkBunVersionEnv(env);
  const found = resolve();
  if (!found) {
    fail(
      `bun@${PINNED_BUN_VERSION} not found on PATH. Install it before running npm scripts ` +
        `(CI: oven-sh/setup-bun@v2 with bun-version: ${PINNED_BUN_VERSION}). ` +
        `This dispatcher never downloads toolchains; provision Bun via oven-sh/setup-bun instead.`,
    );
  }
  if (found.version !== PINNED_BUN_VERSION && env?.HYDRA_ALLOW_BUN_DRIFT !== "1") {
    fail(
      `found bun ${found.version} (${found.bin}) but pinned version is ${PINNED_BUN_VERSION}. ` +
        `Install the pinned version, or set HYDRA_ALLOW_BUN_DRIFT=1 to explicitly consent to drift.`,
    );
  }
  if (found.version !== PINNED_BUN_VERSION) {
    log(`warning: bun drift explicitly allowed (HYDRA_ALLOW_BUN_DRIFT=1): found ${found.version}, pinned ${PINNED_BUN_VERSION}.`);
  } else {
    log(`found bun ${found.version} (${found.bin})`);
  }
  return found;
}

/**
 * Exact command table. Each entry is an ordered list of fail-fast steps;
 * each step is `{ args }` invoked as `spawnSync(bunBin, args)` with no shell.
 * Multi-step entries preserve the original `a && b` semantics sequentially.
 */
export function getCommands(bunBin) {
  void bunBin;
  return {
    dev: [{ args: ["run", "--filter", "@hydra/web", "dev"] }],
    build: [
      { args: ["run", "--filter", "@hydra/web", "build"] },
      { args: ["run", "--filter", "@hydra/chrome-extension", "build"] },
    ],
    test: [{ args: ["test", "apps/web/src", "apps/chrome-extension/src"] }],
    "test:e2e": [{ args: ["run", "--filter", "@hydra/web", "test:e2e"] }],
    typecheck: [
      { args: ["run", "--filter", "@hydra/web", "typecheck"] },
      { args: ["run", "--filter", "@hydra/chrome-extension", "typecheck"] },
    ],
    // Semantically identical to `bun run typecheck`; expanded to avoid
    // recursing through this wrapper (see header comment).
    lint: [
      { args: ["run", "--filter", "@hydra/web", "typecheck"] },
      { args: ["run", "--filter", "@hydra/chrome-extension", "typecheck"] },
    ],
  };
}

/**
 * Run steps sequentially with fail-fast semantics. Never uses a shell.
 * Throws on first non-zero status; returns after all steps succeed.
 */
export function runSteps({ bunBin, steps, label, spawn = spawnSync, env = process.env }) {
  let index = 0;
  for (const step of steps) {
    index += 1;
    log(`run (${label} ${index}/${steps.length}): bun ${step.args.join(" ")}`);
    const r = spawn(bunBin, [...step.args], {
      encoding: "utf8",
      timeout: 600000,
      env,
      stdio: "inherit",
      shell: false,
    });
    const status = typeof r?.status === "number" ? r.status : 1;
    if (status !== 0) {
      const err = new Error(`${label} failed with exit=${status} (fail-fast, step ${index}/${steps.length}).`);
      err.code = status;
      err.step = index;
      throw err;
    }
  }
}

export function parseCommand(argv = process.argv.slice(2)) {
  const [cmd = "build", ...rest] = argv;
  if (!ALLOWED_COMMANDS.includes(cmd)) {
    const err = new Error(
      `unknown command ${JSON.stringify(cmd)} (expected one of: dev, build, test, test:e2e, typecheck, lint). Args: ${rest.join(" ")}`,
    );
    err.code = 1;
    throw err;
  }
  return { cmd, rest };
}

/**
 * Dispatch one command. Dependency-injectable for tests (no globals mutated).
 * NOTE: no HYDRA_SKIP_* handling by design — required checks always run.
 */
export function dispatch(
  cmd,
  { env = process.env, platform = process.platform, spawn = spawnSync, resolve = resolveBun } = {},
) {
  const { cmd: parsed } = parseCommand([cmd]);
  const bun = ensureBun({ env, resolve: () => resolve({ platform, spawn }) });
  if (parsed === "--ensure") return { ok: true, bun, steps: [] };
  const table = getCommands(bun.bin);
  const steps = table[parsed];
  if (!steps) {
    const err = new Error(`unhandled command ${JSON.stringify(parsed)}`);
    err.code = 1;
    throw err;
  }
  runSteps({ bunBin: bun.bin, steps, label: parsed, spawn, env });
  return { ok: true, bun, steps };
}

function main() {
  let cmd = "build";
  try {
    ({ cmd } = parseCommand(process.argv.slice(2)));
  } catch (err) {
    fail(err.message, typeof err.code === "number" && err.code !== 0 ? err.code : 1);
  }
  try {
    dispatch(cmd, { env: process.env, platform: process.platform, spawn: spawnSync, resolve: resolveBun });
  } catch (err) {
    const code = typeof err?.code === "number" && err.code !== 0 ? err.code : 1;
    fail(err?.message ?? String(err), code);
  }
}

const isMain = (() => {
  try {
    return path.resolve(process.argv[1] ?? "") === fileURLToPath(import.meta.url);
  } catch {
    return false;
  }
})();

if (isMain) main();

// Re-export for test introspection without side effects.
export const __internal = { STRICT_VERSION_RE };