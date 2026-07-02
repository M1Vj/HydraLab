import { describe, expect, test } from "bun:test";
import type { ConsoleAllowlist } from "../../lib/api";
import { COMMAND_NOT_ALLOWED, classifyConsoleCommand, verificationDisabled } from "./consoleController";

const allowlist: ConsoleAllowlist = {
  git_inspection: ["git status", "git diff", "git log", "git branch"],
  verification: ["typecheck", "lint", "test", "build"],
  offline: false,
};

describe("safe console classification (HL-SAFE-02)", () => {
  test("read-only git is allowed", () => {
    expect(classifyConsoleCommand("git status", allowlist)).toBe("git");
    expect(classifyConsoleCommand("  git   status ", allowlist)).toBe("git");
  });
  test("verification names are recognized", () => {
    expect(classifyConsoleCommand("test", allowlist)).toBe("verification");
  });
  test("arbitrary shell is rejected", () => {
    expect(classifyConsoleCommand("rm -rf ~/research", allowlist)).toBe("rejected");
    expect(classifyConsoleCommand("git reset --hard", allowlist)).toBe("rejected");
    expect(classifyConsoleCommand("npm install", allowlist)).toBe("rejected");
  });
  test("rejection message mirrors the backend", () => {
    expect(COMMAND_NOT_ALLOWED).toBe("command not allowed");
  });
});

describe("offline posture (HL-SAFE-03)", () => {
  test("verification disabled offline, git still allowed", () => {
    const offline: ConsoleAllowlist = { ...allowlist, offline: true };
    expect(verificationDisabled(offline, "test")).toBe(true);
    expect(classifyConsoleCommand("git status", offline)).toBe("git");
  });
});
