import type { CitationRecord, ClaimRecord, EvidenceRecord, ReviewItem, SourceRecord } from "../../lib/api";

export type StatusTone = "ok" | "warn" | "danger" | "muted";

export type StatusBadge = {
  label: string;
  tone: StatusTone;
  // Non-color-only indicator so status is legible without relying on color.
  symbol: string;
};

// HL-CITE-13: claim status surface renders weak/unsupported/missing indicators.
export function claimStatusBadge(claim: Pick<ClaimRecord, "status" | "link_state">): StatusBadge {
  if (claim.link_state === "target_trashed") {
    return { label: "Trashed source", tone: "danger", symbol: "⊘" };
  }
  switch (claim.status) {
    case "supported":
      return { label: "Supported", tone: "ok", symbol: "✓" };
    case "weak":
      return { label: "Weak", tone: "warn", symbol: "~" };
    case "contradicted":
      return { label: "Contradicted", tone: "danger", symbol: "✗" };
    case "rejected":
      return { label: "Rejected", tone: "muted", symbol: "–" };
    case "needs_review":
      return { label: "Needs review", tone: "warn", symbol: "?" };
    case "draft":
    default:
      return { label: "Unsupported (draft)", tone: "warn", symbol: "!" };
  }
}

// HL-CITE-13: citation inspector flags missing bibliographic metadata.
export function citationMissingMetadata(source: Pick<SourceRecord, "authors" | "year" | "doi" | "csl_json"> | undefined): string[] {
  if (!source) return ["source"];
  const missing: string[] = [];
  if (!source.authors || source.authors.trim() === "") missing.push("authors");
  if (!source.year || String(source.year).trim() === "") missing.push("year");
  if (!source.doi) missing.push("doi");
  return missing;
}

export function evidenceSupportBadge(evidence: Pick<EvidenceRecord, "support" | "support_level">): StatusBadge {
  const level = (evidence.support_level || evidence.support || "").toLowerCase();
  if (level.startsWith("support")) return { label: "Supports", tone: "ok", symbol: "✓" };
  if (level.startsWith("contradict")) return { label: "Contradicts", tone: "danger", symbol: "✗" };
  if (level.startsWith("weak")) return { label: "Weak", tone: "warn", symbol: "~" };
  return { label: "Unsupported", tone: "warn", symbol: "!" };
}

export type InlineBadge = {
  kind: "duplicate" | "broken-link" | "candidate";
  label: string;
  reviewItemId: string;
  targetId?: string | null;
};

// HL-CITE-12: fuzzy-merge / broken-link / candidate items render inline on the
// source they concern, each linking back to its origin.
export function inlineBadgesForSource(reviewItems: ReviewItem[], sourceId: string): InlineBadge[] {
  const badges: InlineBadge[] = [];
  for (const item of reviewItems) {
    const touchesSource = item.origin_id === sourceId || item.target_id === sourceId;
    if (!touchesSource) continue;
    if (item.item_type === "duplicate-merge-proposal") {
      badges.push({ kind: "duplicate", label: "Possible duplicate — review merge", reviewItemId: item.id, targetId: item.target_id });
    } else if (item.item_type === "broken-link") {
      badges.push({ kind: "broken-link", label: "Broken link", reviewItemId: item.id, targetId: item.target_id });
    } else if (item.item_type === "annotation-claim-suggestion") {
      badges.push({ kind: "candidate", label: "Claim candidate", reviewItemId: item.id, targetId: item.target_id });
    }
  }
  return badges;
}

export type CitationEvidenceSummary = {
  claims: number;
  citations: number;
  evidence: number;
  unsupportedClaims: number;
  isEmpty: boolean;
};

export function summarizeCitationEvidence(objects: {
  claims: ClaimRecord[];
  citations: CitationRecord[];
  evidence: EvidenceRecord[];
}): CitationEvidenceSummary {
  const unsupported = objects.claims.filter((claim) => claimStatusBadge(claim).tone !== "ok").length;
  return {
    claims: objects.claims.length,
    citations: objects.citations.length,
    evidence: objects.evidence.length,
    unsupportedClaims: unsupported,
    isEmpty: objects.claims.length === 0 && objects.citations.length === 0 && objects.evidence.length === 0,
  };
}
