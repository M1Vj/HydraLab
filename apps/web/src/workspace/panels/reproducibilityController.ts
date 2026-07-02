import type {
  ReproducibilityBundleResponse,
  ReproducibilityPreviewResponse,
  ReproducibilityRunSummary,
} from "../../lib/api";

export function canBuildBundle(runs: ReproducibilityRunSummary[], selectedRunIds: string[]): boolean {
  const available = new Set(runs.map((run) => run.id));
  return selectedRunIds.length > 0 && selectedRunIds.every((id) => available.has(id));
}

export function includedCategoryLabels(preview: ReproducibilityPreviewResponse): string[] {
  return preview.included_categories.filter((category) => category.count > 0).map((category) => category.label);
}

export function reviewRedactionCount(preview: ReproducibilityPreviewResponse): number {
  return preview.redacted_item_count;
}

export function buildBundleRequest(projectId: string, runIds: string[], approvalId?: string | null) {
  return { project_id: projectId, run_ids: [...runIds], approval_id: approvalId ?? null };
}

export function buildResultMessage(result: ReproducibilityBundleResponse): string {
  return `Built ${result.bundle_id} (${result.manifest_content_hash})`;
}
