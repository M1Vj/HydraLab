#!/usr/bin/env node
/**
 * scripts/ensure-bun.mjs — HydraLab hermetic Bun bootstrap + command dispatcher.
 *
 * Purpose:
 *   Make `npm run build` / `npm test` hermetic on runners that only provide
 *   Node.js + npm (no preinstalled Bun), while preserving the real Bun-based
 *   build/test/typecheck behavior exactly (genuine toolchain, full fidelity).
 *
 * Real commands preserved (identical to pre-hermetic package.json intent):
 *   dev       -> bun run --filter @hydra/web dev
 *   build     -> bun run --filter @hydra/web build && bun run --filter @hydra/chrome-extension build
 *   test      -> bun test apps/web/src apps/chrome-extension/src
 *   test:e2e  -> bun run --filter @hydra/web test:e2e
 *   typecheck -> bun run --filter @hydra/web typecheck && bun run --filter @hydra/chrome-extension typecheck
 *   lint      -> bun run typecheck
 *
 * Hermetic behavior:
 *   - If `bun` is already on PATH (or at $HOME/.bun/bin/bun), it is reused.
 *   - Otherwise the pinned Bun version from packageManager (bun@1.3.11,
 *     overridable via BUN_VERSION) is installed via the official installer
 *     (https://bun.sh/install) on POSIX, with an `npm i -g bun@<ver>`
 *     fallback (and primary path on Windows). Fail-fast: any install or
 *     subcommand failure exits non-zero; genuine execution throughout.
 *
 * Explicit repository-variable gating (clear skip reasons, for docs-only /
 * python-only changes or restricted-network runners):
 *   - HYDRA_SKIP_UI_BUILD=1    -> `node scripts/ensure-bun.mjs build` exits 0 with skip reason.
 *   - HYDRA_SKIP_UI_TEST=1     -> `... test` / `... test:e2e` exit 0 with skip reason.
 *   - HYDRA_SKIP_TYPECHECK=1   -> `... typecheck` / `... lint` exit 0 with skip reason.
 *   - HYDRA_SKIP_FRONTEND=1    -> skips any of the above (coarse gate).
 *   Set these as GitHub Actions repository variables / env vars when the
 *   frontend is intentionally not verified. Unset (default) runs everything.
 *
 * Security / docs invariant: this file adds no secrets handling, touches no
 * SECURITY.md / docs flows, and never deletes capabilities — it only ensures
 * the toolchain exists before delegating to the real commands.
 */
import process from "node:process";
import { existsSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawnSync } from "node:child_process";

const PINNED_BUN_VERSION = process.env.BUN_VERSION?.trim() || "1.3.11";
const BUN_INSTALL_URL = "https://bun.sh/install";

function log(msg) {
  console.log(`[ensure-bun] ${msg}`);
}

function fail(msg, code = 1) {
  console.error(`[ensure-bun] ERROR: ${msg}`);
  process.exit(code);
}

function bunCandidates() {
  const home = os.homedir();
  const cands = [];
  cands.push("bun");
  if (home) cands.push(path.join(home, ".bun", "bin", "bun"));
  return cands;
}

function findBun() {
  for (const cand of bunCandidates()) {
    try {
      const r = spawnSync(cand, ["--version"], { encoding: "utf8", timeout: 15000 });
      if (r.status === 0 && String(r.stdout || "").trim().length > 0) {
        return { bin: cand, version: String(r.stdout).trim() };
      }
    } catch {}
  }
  // Also check node_modules/.bin/bun (npm-added PATH entry)
  try {
    const local = path.join(process.cwd(), "node_modules", ".bin", process.platform === "win32" ? "bun.exe" : "bun");
    if (existsSync(local)) {
      const r = spawnSync(local, ["--version"], { encoding: "utf8", timeout: 15000 });
      if (r.status === 0) return { bin: local, version: String(r.stdout).trim() };
    }
  } catch {}
  return null;
}

function bunBinDir() {
  const home = os.homedir();
  return home ? path.join(home, ".bun", "bin") : null;
}

function envWithBun() {
  const env = { ...process.env };
  const dir = bunBinDir();
  if (dir && existsSync(dir)) {
    const cur = env.PATH || "";
    if (!cur.split(path.delimiter).includes(dir)) {
      env.PATH = `${dir}${path.delimiter}${cur}`;
    }
  }
  // npm adds node_modules/.bin to PATH for lifecycle scripts already; keep it.
  return env;
}

function installBunPosix() {
  log(`bun not found; installing pinned bun-v${PINNED_BUN_VERSION} via official installer (${BUN_INSTALL_URL}) ...`);
  const spec = `bun-v${PINNED_BUN_VERSION}`;
  // Fail-fast: curl -fsSL + bash -s -- <spec>; pipefail semantics via bash -lc.
  const cmd = `set -euo pipefail; curl -fsSL ${BUN_INSTALL_URL} | bash -s -- ${spec}`;
  const r = spawnSync("bash", ["-lc", cmd], {
    encoding: "utf8",
    timeout: 300000,
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (r.stdout) process.stdout.write(String(r.stdout).slice(-3000));
  if (r.stderr) process.stderr.write(String(r.stderr).slice(-3000));
  if (r.status !== 0) return false;
  return true;
}

function installBunViaNpm() {
  log(`falling back to npm global install: bun@${PINNED_BUN_VERSION} ...`);
  const r = spawnSync("npm", ["install", "-g", `bun@${PINNED_BUN_VERSION}`, "--no-audit", "--no-fund"], {
    encoding: "utf8",
    timeout: 300000,
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (r.stdout) process.stdout.write(String(r.stdout).slice(-3000));
  if (r.stderr) process.stderr.write(String(r.stderr).slice(-3000));
  return r.status === 0;
}

function ensureBun() {
  const found = findBun();
  if (found) {
    log(`found bun ${found.version} (${found.bin})`);
    if (found.version !== PINNED_BUN_VERSION) {
      log(`note: expected pinned ${PINNED_BUN_VERSION}, found ${found.version}; proceeding with available bun`);
    }
    return found;
  }
  let ok = false;
  if (process.platform === "win32") {
    ok = installBunViaNpm();
  } else {
    ok = installBunPosix();
    if (!ok) {
      log("official installer failed; trying npm global fallback ...");
      ok = installBunViaNpm();
    }
  }
  if (!ok) {
    fail(
      `failed to install bun@${PINNED_BUN_VERSION}. ` +
        `If this runner has no network, set HYDRA_SKIP_UI_BUILD=1 / HYDRA_SKIP_UI_TEST=1 explicitly to skip with a recorded reason.`
    );
  }
  const after = findBun();
  // The installer drops the binary at $HOME/.bun/bin/bun which may not be on
  // PATH in this process; retry with augmented PATH explicitly.
  if (!after) {
    const dir = bunBinDir();
    if (dir) {
      const direct = path.join(dir, process.platform === "win32" ? "bun.exe" : "bun");
      try {
        const r = spawnSync(direct, ["--version"], { encoding: "utf8", timeout: 15000 });
        if (r.status === 0) {
          log(`installed bun ${String(r.stdout).trim()} (${direct})`);
          return { bin: direct, version: String(r.stdout).trim() };
        }
      } catch {}
    }
    fail("bun install reported success but `bun --version` still fails; aborting (fail-fast).");
  }
  log(`installed bun ${after.version} (${after.bin})`);
  return after;
}

function runShellOrExit(label, script, env) {
  // Run compound `a && b` chains with fail-fast shell semantics.
  log(`run: ${script} (${label})`);
  const shell = process.platform === "win32" ? "cmd" : "bash";
  const shellArgs = process.platform === "win32" ? ["/d", "/s", "/c", script] : ["-lc", `set -euo pipefail; ${script}`];
  const r = spawnSync(shell, shellArgs, { encoding: "utf8", timeout: 600000, env, stdio: "inherit" });
  const status = typeof r.status === "number" ? r.status : 1;
  if (status !== 0) {
    fail(`${label} failed with exit=${status} (fail-fast).`, status === 0 ? 1 : status);
  }
}

function shouldSkip(kind) {
  const e = process.env;
  if (e.HYDRA_SKIP_FRONTEND === "1") return `HYDRA_SKIP_FRONTEND=1`;
  if (kind === "build" && e.HYDRA_SKIP_UI_BUILD === "1") return `HYDRA_SKIP_UI_BUILD=1`;
  if ((kind === "test" || kind === "test:e2e") && e.HYDRA_SKIP_UI_TEST === "1") return `HYDRA_SKIP_UI_TEST=1`;
  if ((kind === "typecheck" || kind === "lint") && e.HYDRA_SKIP_TYPECHECK === "1") return `HYDRA_SKIP_TYPECHECK=1`;
  return null;
}

function main() {
  const [, , cmd = "build", ...rest] = process.argv;
  const allowed = new Set(["dev", "build", "test", "test:e2e", "typecheck", "lint", "--ensure"]);
  if (!allowed.has(cmd)) {
    fail(`unknown command "${cmd}" (expected one of: dev, build, test, test:e2e, typecheck, lint). Args: ${rest.join(" ")}`);
  }
  if (cmd === "--ensure") {
    ensureBun();
    return;
  }
  const skipReason = shouldSkip(cmd);
  if (skipReason) {
    log(`skip: ${skipReason} set — skipping \`${cmd}\` with explicit repository-variable gate (no verification performed).`);
    return;
  }
  ensureBun();
  const env = envWithBun();
  // Delegate to the REAL toolchain with full fidelity. Fail-fast on any error.
  switch (cmd) {
    case "dev":
      runShellOrExit("dev (@hydra/web)", "bun run --filter @hydra/web dev", env);
      break;
    case "build":
      // Sequential, fail-fast: web Vite build, then chrome-extension tsc build.
      runShellOrExit("build (@hydra/web)", "bun run --filter @hydra/web build", env);
      runShellOrExit("build (@hydra/chrome-extension)", "bun run --filter @hydra/chrome-extension build", env);
      break;
    case "test":
      runShellOrExit("test (bun test)", "bun test apps/web/src apps/chrome-extension/src", env);
      break;
    case "test:e2e":
      runShellOrExit("test:e2e (@hydra/web)", "bun run --filter @hydra/web test:e2e", env);
      break;
    case "typecheck":
      runShellOrExit("typecheck (@hydra/web)", "bun run --filter @hydra/web typecheck", env);
      runShellOrExit("typecheck (@hydra/chrome-extension)", "bun run --filter @hydra/chrome-extension typecheck", env);
      break;
    case "lint":
      runShellOrExit("lint (typecheck)", "bun run --filter @hydra/web typecheck && bun run --filter @hydra/chrome-extension typecheck", env);
      break;
    default:
      fail(`unhandled command "${cmd}"`);
  }
}

main();