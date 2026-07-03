import { describe, expect, test } from "bun:test";
import type {
  DocxAvailabilityResponse,
  LatexAvailabilityResponse,
  ManuscriptFormat,
  ManuscriptPackageResponse,
  ManuscriptFormatResponse,
} from "../../lib/api";
import {
  allowedDocxActions,
  docxActionState,
  exposesNativeDocxEditControls,
  exportPreviewState,
  formatRows,
  formatValidationMessage,
  isLatexFile,
  latexCompileState,
  manuscriptPackageBlockers,
} from "./writingFormats";

const BASE_FORMAT: ManuscriptFormat = {
  citation_style: "apa",
  font_family: "Times New Roman",
  font_size: "12pt",
  line_spacing: 1,
  paragraph_spacing: "0pt",
  margins: "1in",
  page_size: "letter",
  orientation: "portrait",
  heading_numbering: false,
  title_page: true,
  abstract: true,
  columns: 1,
  figure_caption: "below",
  table_caption: "above",
  reference_format: "hanging",
  page_numbers: true,
  headers_footers: false,
  manuscript_template: "generic-academic",
  docx_template: "generic-academic",
};

describe("writing formats + DOCX controller", () => {
  test("Phase 1 offers only import/view/export and no native edit controls (HL-WRITE-21)", () => {
    expect(allowedDocxActions().sort()).toEqual(["export", "import", "view"]);
    expect(exposesNativeDocxEditControls(allowedDocxActions())).toBe(false);
    expect(exposesNativeDocxEditControls(["paragraph"])).toBe(true);
    expect(exposesNativeDocxEditControls(["style", "run"])).toBe(true);
  });

  test("DOCX action shows setup state when no converter is available (HL-EXPORT-08)", () => {
    const absent: DocxAvailabilityResponse = {
      adapter: "none",
      version: "",
      availability_status: "unavailable",
      available: false,
      setup_error: "No local DOCX converter is installed.",
    };
    const state = docxActionState(absent);
    expect(state.kind).toBe("setup");
    if (state.kind === "setup") expect(state.message).toContain("No local DOCX converter");
    // Null availability also degrades to setup, never a fake ready state.
    expect(docxActionState(null).kind).toBe("setup");
  });

  test("DOCX action is ready when a converter is detected (HL-EXPORT-09)", () => {
    const present: DocxAvailabilityResponse = {
      adapter: "python-docx",
      version: "1.2.0",
      availability_status: "available",
      available: true,
      setup_error: "",
    };
    const state = docxActionState(present);
    expect(state.kind).toBe("ready");
    if (state.kind === "ready") expect(state.adapter).toBe("python-docx");
  });

  test("LaTeX compile shows setup state when no toolchain is installed (HL-WRITE-19)", () => {
    const absent: LatexAvailabilityResponse = { available: false, toolchain: "", path: "", setup_error: "No TeX toolchain detected." };
    const state = latexCompileState(absent);
    expect(state.kind).toBe("setup");
    if (state.kind === "setup") expect(state.message).toContain("TeX toolchain");
    const present: LatexAvailabilityResponse = { available: true, toolchain: "pdflatex", path: "/usr/bin/pdflatex", setup_error: "" };
    expect(latexCompileState(present).kind).toBe("ready");
  });

  test("format rows mark manuscript overrides against global defaults (HL-WRITE-17/18)", () => {
    const overridden: ManuscriptFormat = { ...BASE_FORMAT, margins: "0.75in", heading_numbering: true };
    const rows = formatRows(overridden, BASE_FORMAT);
    const margins = rows.find((row) => row.label === "Margins");
    const font = rows.find((row) => row.label === "Font family");
    expect(margins?.value).toBe("0.75in");
    expect(margins?.overridden).toBe(true);
    expect(font?.overridden).toBe(false);
    // Full appearance model is surfaced, not only the citation style.
    expect(rows.length).toBeGreaterThan(10);
    expect(rows.some((row) => row.label === "Page size")).toBe(true);
  });

  test("malformed paper.yaml surfaces a validation message naming the key (HL-WRITE-15)", () => {
    const response: ManuscriptFormatResponse = {
      manuscript: "bad",
      format: BASE_FORMAT,
      validation_error: { key: "page_size", message: "invalid page_size 'A99'" },
      source: "global",
    };
    const message = formatValidationMessage(response);
    expect(message).toContain("page_size");
    expect(formatValidationMessage({ ...response, validation_error: null })).toBeNull();
  });

  test("latex file detection", () => {
    expect(isLatexFile("main.tex")).toBe(true);
    expect(isLatexFile("draft.md")).toBe(false);
  });

  test("export preview state reports empty, loading, failure, and ready states (HL-WRITE-32)", () => {
    expect(exportPreviewState({ active: null, loading: false, error: null, preview: null })).toBe("empty");
    expect(exportPreviewState({ active: "paper", loading: true, error: null, preview: null })).toBe("loading");
    expect(exportPreviewState({ active: "paper", loading: false, error: new Error("nope"), preview: null })).toBe("failure");
    expect(exportPreviewState({ active: "paper", loading: false, error: null, preview: previewFixture() })).toBe("ready");
  });

  test("package blockers require citation and redaction acknowledgement (HL-WRITE-34/38)", () => {
    const preview = previewFixture({
      validation: { unresolved_citation_keys: ["missing"], missing_metadata: [], has_issues: true },
      redaction: {
        has_unresolved: true,
        items: [{ id: "redact-1", category: "internal_logs", path: ".hydralab/logs/run.log", reason: "log", decision: "remove-or-acknowledge" }],
      },
    });

    expect(manuscriptPackageBlockers(preview, false, [])).toEqual(["citation-validation", "redaction"]);
    expect(manuscriptPackageBlockers(preview, true, ["redact-1"])).toEqual([]);
  });
});

function previewFixture(overrides: Partial<ManuscriptPackageResponse> = {}): ManuscriptPackageResponse {
  return {
    status: "preview",
    document: {
      manuscript_id: "paper",
      source_dir: "writing/manuscripts/paper",
      format: BASE_FORMAT,
      template_id: "generic-academic",
      sections: [],
      figures: [],
      tables: [],
      citation_keys: [],
      references: {},
      source_files: [],
      include_paths: [],
      authorship_ledger: [],
    },
    validation: { unresolved_citation_keys: [], missing_metadata: [], has_issues: false },
    redaction: { items: [], has_unresolved: false },
    outputs: {},
    package_dir: null,
    manifest_path: "",
    gate: null,
    ...overrides,
  };
}
