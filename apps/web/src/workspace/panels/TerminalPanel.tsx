import { useEffect, useRef, useState } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { TerminalSquare } from "lucide-react";
import { api, type ConsoleAllowlist, type ConsoleRunResult } from "../../lib/api";
import type { PanelComponentProps } from "../panelRegistry";
import { useWorkspaceData } from "../data";
import { PanelScaffold } from "./PanelState";
import { COMMAND_NOT_ALLOWED, classifyConsoleCommand } from "./consoleController";

/**
 * Read-only terminal output (xterm.js) plus a bounded safe command console.
 * xterm.js only renders bytes — it never grants a shell. Input is a separate
 * field wired to the fixed server allowlist; off-list commands are rejected with
 * `command not allowed` and spawn nothing (HL-SAFE-01/02/03).
 */
export function TerminalPanel({ announce }: PanelComponentProps) {
  const { events } = useWorkspaceData();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<XTerm | null>(null);
  const [command, setCommand] = useState("");
  const [allowlist, setAllowlist] = useState<ConsoleAllowlist | null>(null);
  const [pendingApproval, setPendingApproval] = useState<string | null>(null);

  useEffect(() => {
    if (!hostRef.current) return;
    const term = new XTerm({ convertEol: true, disableStdin: true, fontSize: 12, rows: 12, theme: { background: "#0b0e14" } });
    term.open(hostRef.current);
    term.writeln("HydraLab safe console — read-only output. Verification + read-only git only.");
    termRef.current = term;
    return () => term.dispose();
  }, []);

  useEffect(() => {
    void api.get<ConsoleAllowlist>("/api/console/allowlist").then(setAllowlist).catch(() => setAllowlist(null));
  }, []);

  useEffect(() => {
    const term = termRef.current;
    if (!term) return;
    for (const event of (events.data?.events ?? []).slice(0, 40).reverse()) {
      term.writeln(`${event.kind}: ${event.message}`);
    }
  }, [events.data]);

  function print(line: string) {
    termRef.current?.writeln(line);
  }

  async function runCommand(approve = false) {
    const trimmed = command.trim();
    if (!trimmed) return;
    if (allowlist && classifyConsoleCommand(trimmed, allowlist) === "rejected") {
      print(`$ ${trimmed}`);
      print(COMMAND_NOT_ALLOWED);
      announce(COMMAND_NOT_ALLOWED);
      return;
    }
    print(`$ ${trimmed}`);
    try {
      const result = await api.post<ConsoleRunResult>("/api/console/run", { command: trimmed, trigger: "user", approve });
      handleResult(trimmed, result);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught);
      print(`Error: ${message}`);
      announce(`Command failed: ${message}`);
    }
  }

  function handleResult(cmd: string, result: ConsoleRunResult) {
    if (result.status === "approval_required") {
      setPendingApproval(cmd);
      print(result.message ?? `first-use approval required for '${cmd}'`);
      return;
    }
    setPendingApproval(null);
    if (result.status === "rejected") {
      print(result.message ?? COMMAND_NOT_ALLOWED);
    } else if (result.status === "blocked" || result.status === "disabled") {
      print(result.message ?? result.status);
    } else if (result.output !== undefined) {
      print(result.output || "(no output)");
    }
    setCommand("");
  }

  return (
    <PanelScaffold title="Console">
      <div ref={hostRef} className="terminal-host" aria-label="Read-only terminal output" role="log" />
      <form
        className="console-input"
        onSubmit={(event) => {
          event.preventDefault();
          void runCommand(false);
        }}
      >
        <TerminalSquare size={14} aria-hidden />
        <input
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          placeholder="git status | typecheck | lint | test | build"
          aria-label="Safe command console input"
        />
        <button type="submit">Run</button>
        {pendingApproval && (
          <button type="button" onClick={() => void runCommand(true)}>
            Approve &amp; run {pendingApproval}
          </button>
        )}
      </form>
    </PanelScaffold>
  );
}
