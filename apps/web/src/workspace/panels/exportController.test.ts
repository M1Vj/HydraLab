import { describe, expect, test } from "bun:test";
import type { ExportOptionsResponse } from "../../lib/api";
import { DEFAULT_INCLUSION, buildProjectZipRequest, docxSetupRequired, docxSlot } from "./exportController";

const options: ExportOptionsResponse = {
  citation_formats: ["bibtex", "csl", "ris"],
  bundle_formats: [
    { id: "markdown-bundle", label: "Clean Markdown bundle", available: true },
    { id: "project-zip", label: "Project ZIP (selected files)", available: true },
    { id: "docx", label: "DOCX", available: false, state: "setup required", message: "later branch" },
  ],
  opt_in_categories: ["chats", "agent_logs", "browser_snapshots", "annotations"],
  excluded_by_default: [".hydralab/cache", ".git", "secrets/.env"],
};

describe("export options (HL-EXPORT-03)", () => {
  test("docx slot is visible but disabled with setup-required state", () => {
    const slot = docxSlot(options);
    expect(slot).toBeDefined();
    expect(slot?.available).toBe(false);
    expect(docxSetupRequired(options)).toBe(true);
  });
});

describe("project zip request (HL-EXPORT-02/04)", () => {
  test("defaults exclude opt-in categories", () => {
    expect(DEFAULT_INCLUSION.include_chats).toBe(false);
    const req = buildProjectZipRequest(["knowledge/index.md"], DEFAULT_INCLUSION);
    expect(req.selected_files).toEqual(["knowledge/index.md"]);
    expect(req.include_chats).toBe(false);
  });
  test("opt-in toggles pass through", () => {
    const req = buildProjectZipRequest(null, { ...DEFAULT_INCLUSION, include_chats: true });
    expect(req.include_chats).toBe(true);
    expect(req.selected_files).toBeNull();
  });
});
