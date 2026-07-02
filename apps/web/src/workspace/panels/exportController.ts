import type { ExportBundleFormat, ExportOptionsResponse } from "../../lib/api";

export type ExportInclusion = {
  include_chats: boolean;
  include_agent_logs: boolean;
  include_browser_snapshots: boolean;
  include_annotations: boolean;
};

export const DEFAULT_INCLUSION: ExportInclusion = {
  include_chats: false,
  include_agent_logs: false,
  include_browser_snapshots: false,
  include_annotations: false,
};

/** HL-EXPORT-03: locate the DOCX slot, which must be visible but disabled. */
export function docxSlot(options: ExportOptionsResponse): ExportBundleFormat | undefined {
  return options.bundle_formats.find((format) => format.id === "docx");
}

export function docxSetupRequired(options: ExportOptionsResponse): boolean {
  const slot = docxSlot(options);
  return Boolean(slot && slot.available === false && slot.state === "setup required");
}

export function buildProjectZipRequest(selected: string[] | null, inclusion: ExportInclusion) {
  return { selected_files: selected, ...inclusion };
}
