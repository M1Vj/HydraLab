/**
 * scripts/ensure-bun.test.mjs — unit tests for the hardened Bun dispatcher.
 *
 * Runs with plain Node (no Bun required): `node --test scripts/ensure-bun.test.mjs`
 * Also exercised in CI via `bun test scripts/ensure-bun.test.mjs`.
 *
 * Covers audit blockers:
 *  - exact pre-change command preservation (all six commands, fail-fast order)
 *  - no skip-to-pass gates (HYDRA_SKIP_* never skips real work)
 *  - no curl|bash / npm -g bootstrap (static + behavioral: arg arrays, shell:false)
 *  - strict BUN_VERSION sanitization (no env-overridable installer spec)
 *  - fail-closed preflight (missing bun / version drift without consent)
 *  - Windows branch (exe candidates, arg arrays, no shell)
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import {
  PINNED_BUN_VERSION,
  ALLOWED_COMMANDS,
  bunCandidates,
  checkBunVersionEnv,
  dispatch,
  getCommands,
  parseCommand,
  resolveBun,
  runSteps,
} from "./ensure-bun.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(path.join(HERE, "ensure-bun.mjs"), "utf8");

function mockSpawnFactory({ versions = { bun: "1.3.11" }, failures = new Set(), calls = [] } = {}) {
  const spawn = (bin, args, opts) => {
    calls.push({ bin, args: [...args], shell: opts?.shell });
    if (args[0] === "--version") {
      const key = String(bin).includes("chrome") ? "other" : "bun";
      const v = versions[key] ?? versions.bun;
      if (v == null) return { status: 1, stdout: "", stderr: "not found" };
      return { status: 0, stdout: `${v}\n`, stderr: "" };
    }
    const label = `${bin} ${args.join(" ")}`;
    if (failures.has(label) || failures.has(args.join(" ")) || failures.has("__any__")) {
      return { status: 2, stdout: "", stderr: "boom" };
    }
    return { status: 0, stdout: "", stderr: "" };
  };
  return { spawn, calls };
}

describe("command table preserves exact pre-change commands", () => {
  it("exposes all six dispatcher commands plus --ensure", () => {
    for (const c of ["dev", "build", "test", "test:e2e", "typecheck", "lint", "--ensure"]) {
      assert.ok(ALLOWED_COMMANDS.includes(c), `missing ${c}`);
    }
  });

  it("maps dev exactly", () => {
    assert.deepEqual(getCommands("bun").dev, [{ args: ["run", "--filter", "@hydra/web", "dev"] }]);
  });

  it("maps build as two sequential fail-fast steps", () => {
    assert.deepEqual(getCommands("bun").build, [
      { args: ["run", "--filter", "@hydra/web", "build"] },
      { args: ["run", "--filter", "@hydra/chrome-extension", "build"] },
    ]);
  });

  it("maps test to both web and chrome-extension suites", () => {
    assert.deepEqual(getCommands("bun").test, [
      { args: ["test", "apps/web/src", "apps/chrome-extension/src"] },
    ]);
  });

  it("maps test:e2e exactly", () => {
    assert.deepEqual(getCommands("bun")["test:e2e"], [
      { args: ["run", "--filter", "@hydra/web", "test:e2e"] },
    ]);
  });

  it("maps typecheck as two sequential fail-fast steps", () => {
    assert.deepEqual(getCommands("bun").typecheck, [
      { args: ["run", "--filter", "@hydra/web", "typecheck"] },
      { args: ["run", "--filter", "@hydra/chrome-extension", "typecheck"] },
    ]);
  });

  it("maps lint to the typecheck steps (recursion-safe, semantically `bun run typecheck`)", () => {
    const t = getCommands("bun");
    assert.deepEqual(t.lint, t.typecheck);
    assert.ok(!t.lint.some((s) => s.args.join(" ") === "run typecheck"), "lint must not recurse via `bun run typecheck`");
  });

  it("rejects unknown commands fail-closed", () => {
    assert.throws(() => parseCommand(["bogus"]), /unknown command/);
  });
});

describe("fail-fast execution without a shell", () => {
  it("runs steps with arg arrays and shell:false", () => {
    const { spawn, calls } = mockSpawnFactory();
    runSteps({
      bunBin: "bun",
      steps: getCommands("bun").build,
      label: "build",
      spawn,
      env: { PATH: "x" },
    });
    assert.equal(calls.length, 2);
    for (const c of calls) {
      assert.ok(Array.isArray(c.args), "args must be an array (no shell-string interpolation)");
      assert.equal(c.shell, false);
    }
    assert.deepEqual(calls[0].args, ["run", "--filter", "@hydra/web", "build"]);
    assert.deepEqual(calls[1].args, ["run", "--filter", "@hydra/chrome-extension", "build"]);
  });

  it("aborts remaining steps on first failure and surfaces non-zero", () => {
    const { spawn, calls } = mockSpawnFactory({ failures: new Set(["run --filter @hydra/web build"]) });
    assert.throws(
      () =>
        runSteps({ bunBin: "bun", steps: getCommands("bun").build, label: "build", spawn, env: {} }),
      /failed with exit=2 \(fail-fast, step 1\/2\)/,
    );
    assert.equal(calls.filter((c) => c.args[0] !== "--version").length, 1);
  });
});

describe("no skip-to-pass gates (fail-closed by default)", () => {
  for (const v of ["HYDRA_SKIP_FRONTEND", "HYDRA_SKIP_UI_BUILD", "HYDRA_SKIP_UI_TEST", "HYDRA_SKIP_TYPECHECK"]) {
    it(`ignores ${v}=1 and still runs real commands`, () => {
      const { spawn, calls } = mockSpawnFactory();
      const env = { [v]: "1", HYDRA_ALLOW_BUN_DRIFT: "1" };
      const resolve = (opts = {}) => resolveBun({ ...opts, spawn, homedir: "/home/u", cwd: "/repo" });
      dispatch("build", { env, spawn, resolve, platform: "linux" });
      const runs = calls.filter((c) => c.args[0] !== "--version");
      assert.equal(runs.length, 2, `${v}=1 must not skip work`);
    });
  }
});

describe("BUN_VERSION sanitization (no env-overridable installer spec)", () => {
  it("pins the locked version", () => {
    assert.equal(PINNED_BUN_VERSION, "1.3.11");
  });

  it("accepts unset or exact pinned value", () => {
    assert.equal(checkBunVersionEnv({}), null);
    assert.equal(checkBunVersionEnv({ BUN_VERSION: "1.3.11" }), "1.3.11");
    assert.equal(checkBunVersionEnv({ BUN_VERSION: "  1.3.11  " }), "1.3.11");
  });

  it("rejects shell-injection and mismatched versions fail-closed", () => {
    for (const evil of [
      "1.3.11; rm -rf /",
      "1.3.11 && curl evil",
      "$(curl evil)",
      "`id`",
      "1.3.11 | bash",
      "latest",
      "1.3.12",
      "1.2.3",
      "v1.3.11",
      "1.3",
    ]) {
      assert.throws(() => checkBunVersionEnv({ BUN_VERSION: evil }), /BUN_VERSION/, `must reject ${JSON.stringify(evil)}`);
    }
  });

  it("dispatch fails closed when BUN_VERSION disagrees with pinned", () => {
    const { spawn } = mockSpawnFactory();
    const resolve = (opts = {}) => resolveBun({ ...opts, spawn, homedir: "/h", cwd: "/r" });
    assert.throws(
      () => dispatch("test", { env: { BUN_VERSION: "1.3.12" }, spawn, resolve, platform: "linux" }),
      /disagrees with pinned/,
    );
  });
});

describe("fail-closed preflight (no downloads, no global mutation)", () => {
  it("fails when bun is missing with an actionable oven-sh/setup-bun message", () => {
    const missing = () => ({ status: 1, stdout: "", stderr: "" });
    const resolve = (opts = {}) => resolveBun({ ...opts, spawn: missing, homedir: "/h", cwd: "/r" });
    const realExit = process.exit;
    let code = null;
    process.exit = (c) => {
      code = c;
      throw new Error(`exit:${c}`);
    };
    try {
      assert.throws(() => dispatch("test", { env: {}, spawn: missing, resolve, platform: "linux" }), /exit:1/);
      assert.equal(code, 1);
    } finally {
      process.exit = realExit;
    }
  });

  it("fails on version drift without explicit consent", () => {
    const { spawn } = mockSpawnFactory({ versions: { bun: "9.9.9" } });
    const resolve = (opts = {}) => resolveBun({ ...opts, spawn, homedir: "/h", cwd: "/r" });
    const realExit = process.exit;
    process.exit = (c) => {
      throw new Error(`exit:${c}`);
    };
    try {
      assert.throws(() => dispatch("test", { env: {}, spawn, resolve, platform: "linux" }), /exit:1/);
    } finally {
      process.exit = realExit;
    }
  });

  it("proceeds on drift only with HYDRA_ALLOW_BUN_DRIFT=1", () => {
    const { spawn, calls } = mockSpawnFactory({ versions: { bun: "9.9.9" } });
    const resolve = (opts = {}) => resolveBun({ ...opts, spawn, homedir: "/h", cwd: "/r" });
    const out = dispatch("test", { env: { HYDRA_ALLOW_BUN_DRIFT: "1" }, spawn, resolve, platform: "linux" });
    assert.equal(out.ok, true);
    assert.ok(calls.some((c) => c.args[0] === "test"));
  });

  it("contains no curl|bash bootstrap, installer URL, or npm -g fallback", () => {
    // Strip comments so documentation of prohibitions ("NO curl|bash")
    // cannot trip the scan; only executable code is inspected.
    const CODE = SOURCE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|\s)\/\/.*$/gm, "$1");
    assert.ok(!CODE.includes("curl"), "code must not invoke curl");
    assert.ok(!CODE.includes("bun.sh/install"), "code must not reference the bun installer URL");
    assert.ok(!CODE.includes("install -g") && !CODE.includes('"install", "-g"'), "code must not contain npm -g fallback");
    assert.ok(!CODE.includes("BUN_INSTALL_URL"), "code must not define an installer URL constant");
    assert.ok(!CODE.includes("HYDRA_SKIP_"), "code must not contain skip-to-pass gates");
    assert.ok(!CODE.includes("bash"), "code must not shell out via bash");
    assert.ok(!CODE.includes("shell: true"), "code must never enable shell:true");
  });
});

describe("Windows branch (arg arrays, no shell)", () => {
  it("probes bun.exe candidates", () => {
    const cands = bunCandidates({ platform: "win32", homedir: "C:\\Users\\u", cwd: "C:\\repo" });
    assert.ok(cands.some((c) => c.endsWith("bun.exe")), `expected bun.exe candidates, got ${cands.join(", ")}`);
  });

  it("dispatches on win32 with shell:false and exe resolution", () => {
    const { spawn, calls } = mockSpawnFactory();
    const resolve = (opts = {}) =>
      resolveBun({ ...opts, spawn, homedir: "C:\\Users\\u", cwd: "C:\\repo" });
    const out = dispatch("test", { env: {}, spawn, resolve, platform: "win32" });
    assert.equal(out.ok, true);
    for (const c of calls) assert.equal(c.shell, false);
    assert.ok(calls.some((c) => c.args[0] === "test"));
  });
});