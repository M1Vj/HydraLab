import type {
  DocxAvailabilityResponse,
  LatexAvailabilityResponse,
  ManuscriptFormat,
  ManuscriptFormatResponse,
} from "../../lib/api";

// Phase-1 DOCX surface is import + view + export ONLY. Full native DOCX editing
// and AI-assisted OpenXML structural edits (paragraph/run/style/comment/tracked
// change targeting) are Phase 2 (branch 02-08) and are intentionally NOT
// offered here (HL-WRITE-21).
export type DocxAction = "import" | "view" | "export";

export function allowedDocxActions(): DocxAction[] {
  return ["import", "view", "export"];
}

// Guard used by the panel + tests: Phase 1 exposes no structural edit controls.
const PHASE2_EDIT_CONTROLS = ["paragraph", "run", "style", "comment", "tracked-change"];

export function exposesNativeDocxEditControls(controls: string[]): boolean {
  return controls.some((control) => PHASE2_EDIT_CONTROLS.includes(control));
}

export type ConverterActionState =
  | { kind: "ready"; adapter: string; version: string }
  | { kind: "setup"; message: string };

// HL-EXPORT-08: when no local converter is available the action shows an honest
// setup/disabled state (never a fake success).
export function docxActionState(availability: DocxAvailabilityResponse | null): ConverterActionState {
  if (!availability || !availability.available) {
    return {
      kind: "setup",
      message:
        availability?.setup_error ||
        "No local DOCX converter is installed. Install python-docx (bundled) or Pandoc to enable DOCX import/export.",
    };
  }
  return { kind: "ready", adapter: availability.adapter, version: availability.version };
}

export type LatexCompileState =
  | { kind: "ready"; toolchain: string }
  | { kind: "setup"; message: string };

// HL-WRITE-19: LaTeX editing is always available; compile/preview is gated behind
// a setup/disabled state that names the missing TeX toolchain.
export function latexCompileState(availability: LatexAvailabilityResponse | null): LatexCompileState {
  if (!availability || !availability.available) {
    return {
      kind: "setup",
      message:
        availability?.setup_error || "No TeX toolchain detected. Install TeX Live / Tectonic to enable LaTeX compile.",
    };
  }
  return { kind: "ready", toolchain: availability.toolchain };
}

export type FormatRow = { label: string; value: string; overridden: boolean };

const FIELD_LABELS: Array<[keyof ManuscriptFormat, string]> = [
  ["citation_style", "Citation style"],
  ["font_family", "Font family"],
  ["font_size", "Font size"],
  ["line_spacing", "Line spacing"],
  ["paragraph_spacing", "Paragraph spacing"],
  ["margins", "Margins"],
  ["page_size", "Page size"],
  ["orientation", "Orientation"],
  ["heading_numbering", "Heading numbering"],
  ["columns", "Columns"],
  ["figure_caption", "Figure captions"],
  ["table_caption", "Table captions"],
  ["reference_format", "Reference format"],
  ["page_numbers", "Page numbers"],
  ["headers_footers", "Headers / footers"],
];

// HL-WRITE-18: surface the full appearance model, marking manuscript overrides
// relative to the global defaults (HL-WRITE-17).
export function formatRows(format: ManuscriptFormat, defaults: ManuscriptFormat | null): FormatRow[] {
  return FIELD_LABELS.map(([key, label]) => ({
    label,
    value: String(format[key]),
    overridden: defaults ? String(format[key]) !== String(defaults[key]) : false,
  }));
}

// HL-WRITE-15: derive a human validation state from the format response.
export function formatValidationMessage(response: ManuscriptFormatResponse | null): string | null {
  if (!response?.validation_error) return null;
  return `Invalid "${response.validation_error.key}" in paper.yaml — using the global default. ${response.validation_error.message}`;
}

export function isLatexFile(name: string): boolean {
  return name.toLowerCase().endsWith(".tex");
}
