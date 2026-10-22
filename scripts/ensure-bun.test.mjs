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
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import vm from "node:vm";

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

// Execute the CLI entry point with synthetic argv/process and a subprocess
// recorder. Only ESM declarations are adapted for the VM; main() is unchanged.
// This proves dispatch wiring, not real Bun/Vite/Playwright integration.
function runCli(argv, { env = {}, platform = "linux", version = "1.3.11", results = [] } = {}) {
  const calls = [];
  const errors = [];
  const entry = path.resolve("/virtual/ensure-bun.mjs");
  const exit = {};
  let code = 0;
  let step = 0;
  const source = SOURCE
    .replace(/^import .*;$/gm, "")
    .replace(/^export /gm, "")
    .replaceAll("import.meta.url", JSON.stringify(pathToFileURL(entry).href));
  try {
    vm.runInNewContext(source, {
      process: {
        argv: ["node", entry, ...argv], env, platform,
        cwd: () => "/virtual",
        exit: (status) => { code = status; throw exit; },
      },
      path, os: { homedir: () => "/empty" }, fileURLToPath,
      console: { log: () => {}, error: (message) => errors.push(message) },
      spawnSync: (bin, args, options) => {
        calls.push({ bin, args: Array.from(args), options: { ...options } });
        if (args[0] === "--version") {
          return version === null ? { status: 1 } : { status: 0, stdout: `${version}\n` };
        }
        return results[step++] ?? { status: 0 };
      },
    }, { timeout: 1000 });
  } catch (error) {
    if (error !== exit) throw error;
  }
  return { code, calls, errors, runs: calls.filter((call) => call.args[0] !== "--version") };
}

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


describe("CLI argument and timeout regressions (mocked subprocesses)", () => {
  it("forwards dev port options and leaves the server unbounded", () => {
    const out = runCli(["dev", "--port", "5174"]);
    assert.equal(out.code, 0);
    assert.deepEqual(out.runs.map((call) => call.args), [["run", "--filter", "@hydra/web", "dev", "--port", "5174"]]);
    assert.equal(out.runs[0].options.timeout, 0);
    assert.equal(out.calls[0].options.timeout, 15000, "the version probe must remain bounded");
  });

  it("forwards test --watch and does not terminate the watcher after ten minutes", () => {
    const out = runCli(["test", "--watch"]);
    assert.equal(out.code, 0);
    assert.deepEqual(out.runs[0].args, ["test", "apps/web/src", "apps/chrome-extension/src", "--watch"]);
    assert.equal(out.runs[0].options.timeout, 0);
  });

  it("forwards test:e2e --list without turning it into a normal test run", () => {
    const out = runCli(["test:e2e", "--list"]);
    assert.equal(out.code, 0);
    assert.deepEqual(out.runs[0].args, ["run", "--filter", "@hydra/web", "test:e2e", "--list"]);
    assert.equal(out.runs[0].options.timeout, 600000);
  });

  for (const cmd of ["build", "typecheck", "lint"]) {
    it(`appends ${cmd} options only to the final step, preserving chained-script semantics`, () => {
      const args = ["--pretty", "false"];
      const script = cmd === "build" ? "build" : "typecheck";
      const out = runCli([cmd, ...args]);
      assert.equal(out.code, 0);
      assert.deepEqual(out.runs.map((call) => call.args), [
        ["run", "--filter", "@hydra/web", script],
        ["run", "--filter", "@hydra/chrome-extension", script, ...args],
      ]);
      assert.deepEqual(out.runs.map((call) => call.options.timeout), [600000, 600000]);
    });

    for (const flag of ["--watch", "-w"]) {
      it(`leaves only the final ${cmd} ${flag} step unbounded`, () => {
        const out = runCli([cmd, flag]);
        assert.equal(out.code, 0);
        assert.deepEqual(out.runs.map((call) => call.options.timeout), [600000, 0]);
        assert.equal(out.runs[1].args.at(-1), flag);
      });
    }
  }

  for (const flag of ["--ui", "--debug"]) {
    it(`leaves Playwright ${flag} interactive mode unbounded`, () => {
      const out = runCli(["test:e2e", flag]);
      assert.equal(out.code, 0);
      assert.equal(out.runs[0].args.at(-1), flag);
      assert.equal(out.runs[0].options.timeout, 0);
    });
  }

  it("preserves empty arguments, whitespace, quotes, separators and metacharacters literally", () => {
    const args = ["", "two words", "'single'", '"double"', "a;b", "$(never-run)", "`never-run`", "&&", "|", "*.test.ts", "a\nb", "--", "--watch"];
    for (const platform of ["linux", "win32"]) {
      const out = runCli(["test", ...args], { platform });
      assert.equal(out.code, 0);
      assert.deepEqual(out.runs[0].args, ["test", "apps/web/src", "apps/chrome-extension/src", ...args]);
      assert.equal(out.runs[0].options.timeout, 600000, "--watch after -- is not an option");
      for (const call of out.calls) assert.equal(call.options.shell, false);
      assert.equal(out.runs[0].options.stdio, "inherit");
    }
  });

  it("keeps one-shot commands bounded and defaults to the unchanged build sequence", () => {
    for (const cmd of ["build", "test", "test:e2e", "typecheck", "lint"]) {
      const out = runCli([cmd]);
      assert.equal(out.code, 0);
      assert.ok(out.runs.every((call) => call.options.timeout === 600000));
      assert.deepEqual(out.runs.map((call) => call.args), getCommands("bun")[cmd].map((step) => step.args));
    }
    assert.deepEqual(runCli([]).runs.map((call) => call.args), getCommands("bun").build.map((step) => step.args));
  });

  it("does not disable the timeout for explicitly disabled compiler watch mode", () => {
    for (const rest of [["--watch", "false"], ["-w", "false"], ["--watch", "--watch", "false"]]) {
      const out = runCli(["typecheck", ...rest]);
      assert.deepEqual(out.runs.map((call) => call.options.timeout), [600000, 600000]);
      assert.deepEqual(out.runs[1].args.slice(4), rest);
    }
  });

  it("rejects an unknown command before resolving or spawning Bun", () => {
    const out = runCli(["unknown", "--watch"]);
    assert.equal(out.code, 1);
    assert.equal(out.calls.length, 0);
    assert.match(out.errors.join("\n"), /unknown command/);
  });

  it("--ensure only probes, even if extra arguments are supplied", () => {
    const out = runCli(["--ensure", "--watch"]);
    assert.equal(out.code, 0);
    assert.equal(out.calls.length, 1);
    assert.equal(out.runs.length, 0);
  });

  it("preserves fail-fast exit codes and never reaches the second build step after failure", () => {
    const out = runCli(["build", "--pretty", "false"], { results: [{ status: 7 }] });
    assert.equal(out.code, 7);
    assert.equal(out.runs.length, 1);
    assert.deepEqual(out.runs[0].args, ["run", "--filter", "@hydra/web", "build"]);
    assert.match(out.errors.join("\n"), /fail-fast, step 1\/2/);
  });

  it("surfaces a failing final step's exit code after forwarding its arguments", () => {
    const out = runCli(["typecheck", "--pretty", "false"], { results: [{ status: 0 }, { status: 9 }] });
    assert.equal(out.code, 9);
    assert.equal(out.runs.length, 2);
    assert.deepEqual(out.runs[1].args.slice(4), ["--pretty", "false"]);
  });

  it("fails closed on missing exit status, signal or spawn failure", () => {
    for (const result of [{}, { status: null, signal: "SIGTERM" }, { status: null, error: { code: "ENOENT" } }]) {
      const out = runCli(["build"], { results: [result] });
      assert.equal(out.code, 1);
      assert.equal(out.runs.length, 1);
    }
  });

  it("keeps missing Bun and version mismatch fail-closed at the CLI boundary", () => {
    for (const setup of [{ version: null }, { version: "9.9.9" }, { env: { BUN_VERSION: "latest" } }]) {
      const out = runCli(["test", "--watch"], setup);
      assert.equal(out.code, 1);
      assert.equal(out.runs.length, 0);
    }
  });
});
