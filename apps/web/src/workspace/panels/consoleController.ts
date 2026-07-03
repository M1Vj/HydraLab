import type { ConsoleAllowlist } from "../../lib/api";

/** Mirrors the backend rejection message (HL-SAFE-02). */
export const COMMAND_NOT_ALLOWED = "command not allowed";

export type ConsoleClassification = "git" | "verification" | "rejected";

/**
 * Client-side pre-check mirroring the server allowlist. The server remains the
 * source of truth (it enforces and spawns); this only avoids a needless round
 * trip and lets the UI show `command not allowed` immediately.
 */
export function classifyConsoleCommand(command: string, allowlist: ConsoleAllowlist): ConsoleClassification {
  const normalized = command.trim().split(/\s+/).join(" ");
  if (allowlist.git_inspection.includes(normalized)) return "git";
  if (allowlist.verification.includes(normalized)) return "verification";
  return "rejected";
}

export function verificationDisabled(allowlist: ConsoleAllowlist, command: string): boolean {
  return allowlist.offline && allowlist.verification.includes(command.trim());
}
