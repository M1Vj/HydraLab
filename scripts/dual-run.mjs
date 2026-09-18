// HydraLab portable dual-runtime dispatcher (bun preferred, npm fallback).
//
// Why this file exists:
// - `if command -v bun ...` in npm scripts is POSIX-only and breaks on
//   Windows runners, and `A && B || C` shell chains mask failures (if B
//   fails, C runs). Node runs everywhere npm runs, and spawnSync status
//   checks are fail-fast.
// - Duplicated shell conditionals across 6 root scripts were a
//   maintainability regression; all branching lives here, once.
// - Root `npm test` MUST cover BOTH apps/web/src AND apps/chrome-extension/src
//   (bun runs `bun test apps/web/src apps/chrome-extension/src`). The npm
//   branch runs web via its workspace script plus chrome-extension via vitest
//   directly, so no edit to apps/chrome-extension/package.json is required.
// - Every branch logs BRANCH=bun or BRANCH=npm-vitest so CI evidence states
//   which runtime was taken (no bare `npm test: passed`).
// - e2e (Playwright, needs browsers/network) is explicitly gated behind
//   HYDRA_RUN_E2E=1 with a clear SKIP reason; unit tests stay hermetic.
// - `verify:lockfile` fails fast when bun.lock/bun.lockb/package-lock.json is
//   missing or stale for pdfjs-dist/vitest, unless
//   HYDRA_ALLOW_MISSING_LOCKFILE=1 (clear SKIP reason). Regenerate with
//   `bun install` (preferred) or `npm install`, then commit the lockfile.
// - `test:equivalence` runs both runners when bun exists and compares results.
//
// Security: no network egress, reads no secrets, only spawns checked-in
// toolchain binaries with inherited stdio. Fail-fast: any child non-zero exit
// propagates as process exit code.
import { spawnSync, execSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");
const task = process.argv[2] || "test";

function hasBun() {
  try {
    execSync("bun --version", { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

function sh(cmd, args, opts = {}) {
  const res = spawnSync(cmd, args, {
    stdio: "inherit",
    shell: false,
    cwd: opts.cwd || ROOT,
    env: process.env,
  });
  return res.status ?? 1;
}

function shShell(line, opts = {}) {
  const res = spawnSync(line, {
    stdio: "inherit",
    shell: true,
    cwd: opts.cwd || ROOT,
    env: process.env,
  });
  return res.status ?? 1;
}

function die(code) {
  process.exit(code === 0 ? 0 : code || 1);
}

function runBunOrNpm({ bun, npm }) {
  if (hasBun()) {
    console.log(`BRANCH=bun task=${task}`);
    die(shShell(bun));
  }
  console.log(`BRANCH=npm-vitest task=${task} (bun not found)`);
  die(shShell(npm));
}

function verifyLockfile() {
  const allowMissing = process.env.HYDRA_ALLOW_MISSING_LOCKFILE === "1";
  const candidates = ["bun.lock", "bun.lockb", "package-lock.json"];
  const found = candidates.filter((f) => existsSync(resolve(ROOT, f)));
  let pkg = {};
  try {
    pkg = JSON.parse(readFileSync(resolve(ROOT, "apps/web/package.json"), "utf8"));
  } catch {}
  const pdfjs = pkg?.dependencies?.["pdfjs-dist"];
  const vitest = pkg?.devDependencies?.["vitest"];
  console.log(`lockfile candidates present: ${found.join(", ") || "(none)"}`);
  console.log(`apps/web pdfjs-dist=${pdfjs} vitest=${vitest}`);
  if (found.length === 0) {
    const msg =
      "SKIP/FAIL verify:lockfile: no bun.lock/bun.lockb/package-lock.json at repo root. " +
      "Regenerate with `bun install` or `npm install` and commit the lockfile. " +
      "pdfjs-dist 6.2.108 + vitest ^3.2.4 must be pinned by the lockfile.";
    if (allowMissing) {
      console.log(`${msg} HYDRA_ALLOW_MISSING_LOCKFILE=1 so continuing with SKIP.`);
      die(0);
    }
    console.error(msg);
    die(1);
  }
  // Best-effort staleness probe: lockfile must mention both pinned deps.
  const hay = found
    .map((f) => {
      try {
        return readFileSync(resolve(ROOT, f), "utf8").slice(0, 2000000);
      } catch {
        return "";
      }
    })
    .join("\n");
  const mentionsPdfjs = hay.includes("pdfjs-dist");
  const mentionsVitest = hay.includes("vitest");
  if ((!mentionsPdfjs || !mentionsVitest) && !allowMissing) {
    console.error(
      `FAIL verify:lockfile: lockfile does not mention pdfjs-dist(${mentionsPdfjs}) / vitest(${mentionsVitest}). Regenerate lockfile.`
    );
    die(1);
  }
  console.log("verify:lockfile: OK");
  die(0);
}

function runE2E() {
  if (process.env.HYDRA_RUN_E2E !== "1") {
    console.log(
      "SKIP test:e2e: hermetic gate — set HYDRA_RUN_E2E=1 to run Playwright e2e (requires browsers + network)."
    );
    die(0);
  }
  if (hasBun()) {
    console.log("BRANCH=bun task=test:e2e");
    die(shShell("bun run --filter @hydra/web test:e2e"));
  }
  console.log("BRANCH=npm-vitest task=test:e2e");
  die(shShell("npm run test:e2e --workspace=@hydra/web"));
}

function runWebE2E() {
  if (process.env.HYDRA_RUN_E2E !== "1") {
    console.log(
      "SKIP test:e2e: hermetic gate — set HYDRA_RUN_E2E=1 to run Playwright e2e (requires browsers + network)."
    );
    die(0);
  }
  const pinned =
    " ../../node_modules/.bun/@playwright+test@1.61.1/node_modules/@playwright/test/cli.js";
  // Preserve the original hermetic pinned runner when present; fall back to
  // PATH-resolved playwright only when the pinned file is absent.
  const fs = awaitImportFs();
  function awaitImportFs() {
    return null;
  }
  void fs;
  const { existsSync: ex } = await import("node:fs");
  const { spawnSync: sp } = await import("node:child_process");
  void sp;
  if (ex(resolve(process.cwd(), pinned.trim()))) {
    die(sh(process.execPath, [resolve(process.cwd(), pinned.trim()), "test"], { cwd: process.cwd() }));
  }
  die(shShell("npx --no-install playwright test", { cwd: process.cwd() }));
}

function testEquivalence() {
  const bun = hasBun();
  if (!bun) {
    console.log("BRANCH=npm-vitest task=test:equivalence (bun absent; running vitest suites only)");
    let code = shShell("npm run test --workspace=@hydra/web");
    if (code !== 0) die(code);
    code = shShell("npx --no-install vitest run --config apps/chrome-extension/vitest.config.ts --root apps/chrome-extension");
    die(code);
  }
  console.log("BRANCH=both task=test:equivalence (running bun then vitest, comparing)");
  const bunCode = shShell("bun test apps/web/src apps/chrome-extension/src");
  const webCode = shShell("npm run test --workspace=@hydra/web");
  const extCode = shShell(
    "npx --no-install vitest run --config apps/chrome-extension/vitest.config.ts --root apps/chrome-extension"
  );
  const vitestCode = webCode === 0 && extCode === 0 ? 0 : 1;
  console.log(`equivalence: bun=${bunCode} vitest=${vitestCode}`);
  if (bunCode !== vitestCode) {
    console.error("FAIL test:equivalence: bun and vitest disagree; investigate before merge.");
    die(1);
  }
  die(bunCode);
}

switch (task) {
  case "dev":
    runBunOrNpm({
      bun: "bun run --filter @hydra/web dev",
      npm: "npm run dev --workspace=@hydra/web",
    });
    break;
  case "build":
    runBunOrNpm({
      bun: "bun run --filter @hydra/web build && bun run --filter @hydra/chrome-extension build",
      npm: "npm run build --workspace=@hydra/web && npm run build --workspace=@hydra/chrome-extension",
    });
    break;
  case "test":
    if (hasBun()) {
      console.log("BRANCH=bun task=test");
      die(shShell("bun test apps/web/src apps/chrome-extension/src"));
    }
    console.log("BRANCH=npm-vitest task=test (bun not found; running BOTH suites)");
    {
      const a = shShell("npm run test --workspace=@hydra/web");
      if (a !== 0) die(a);
      // Chrome-extension suite via vitest directly: hermetic, no edit to its
      // package.json required, preserves capability dropped by earlier fallback.
      die(
        shShell(
          "npx --no-install vitest run --config apps/chrome-extension/vitest.config.ts --root apps/chrome-extension"
        )
      );
    }
    break;
  case "web-test": {
    const cwd = process.cwd();
    if (hasBun()) {
      console.log("BRANCH=bun task=web-test");
      die(sh("bun", ["test", "src"], { cwd }));
    }
    console.log("BRANCH=npm-vitest task=web-test");
    die(sh("npx", ["--no-install", "vitest", "run"], { cwd }));
  }
  case "test:e2e":
    runE2E();
    break;
  case "web-e2e": {
    if (process.env.HYDRA_RUN_E2E !== "1") {
      console.log(
        "SKIP test:e2e: hermetic gate — set HYDRA_RUN_E2E=1 to run Playwright e2e (requires browsers + network)."
      );
      die(0);
    }
    const cwd = process.cwd();
    const pinned = resolve(cwd, "../../node_modules/.bun/@playwright+test@1.61.1/node_modules/@playwright/test/cli.js");
    if (existsSync(pinned)) {
      console.log("BRANCH=pinned-playwright task=web-e2e");
      die(sh(process.execPath, [pinned, "test"], { cwd }));
    }
    console.log("BRANCH=path-playwright task=web-e2e (pinned runner absent)");
    die(sh("npx", ["--no-install", "playwright", "test"], { cwd }));
  }
  case "typecheck":
    runBunOrNpm({
      bun: "bun run --filter @hydra/web typecheck && bun run --filter @hydra/chrome-extension typecheck",
      npm: "npm run typecheck --workspace=@hydra/web && npm run typecheck --workspace=@hydra/chrome-extension",
    });
    break;
  case "lint":
    runBunOrNpm({
      bun: "bun run typecheck",
      npm: "npm run typecheck",
    });
    break;
  case "test:equivalence":
    testEquivalence();
    break;
  case "verify:lockfile":
    verifyLockfile();
    break;
  default:
    console.error(`unknown dual-run task: ${task}`);
    die(1);
}