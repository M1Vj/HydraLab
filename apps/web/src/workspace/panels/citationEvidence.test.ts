import { describe, expect, test } from "bun:test";
import type { ClaimRecord, EvidenceRecord, ReviewItem, SourceRecord } from "../../lib/api";
import {
  citationMissingMetadata,
  claimStatusBadge,
  evidenceSupportBadge,
  inlineBadgesForSource,
  summarizeCitationEvidence,
} from "./citationEvidence";

describe("citation/evidence panel logic", () => {
  test("claim status badge marks unsupported drafts and trashed targets (HL-CITE-13)", () => {
    expect(claimStatusBadge({ status: "draft" }).tone).toBe("warn");
    expect(claimStatusBadge({ status: "supported" }).tone).toBe("ok");
    expect(claimStatusBadge({ status: "weak" }).tone).toBe("warn");
    expect(claimStatusBadge({ status: "contradicted" }).tone).toBe("danger");
    expect(claimStatusBadge({ status: "supported", link_state: "target_trashed" }).tone).toBe("danger");
    // Non-color-only: every badge carries a symbol.
    expect(claimStatusBadge({ status: "draft" }).symbol).toBeTruthy();
  });

  test("citation inspector flags missing bibliographic metadata (HL-CITE-13)", () => {
    const complete: SourceRecord = { id: "s1", title: "Attention", authors: "Vaswani", year: "2017", doi: "10.1/x" };
    expect(citationMissingMetadata(complete)).toEqual([]);
    expect(citationMissingMetadata({ id: "s2", title: "No meta" })).toEqual(["authors", "year", "doi"]);
    expect(citationMissingMetadata(undefined)).toEqual(["source"]);
  });

  test("evidence support badge maps support_level (HL-CITE-10)", () => {
    const ev: Pick<EvidenceRecord, "support" | "support_level"> = { support: "supported", support_level: "supports" };
    expect(evidenceSupportBadge(ev).label).toBe("Supports");
    expect(evidenceSupportBadge({ support: "unsupported" }).tone).toBe("warn");
  });

  test("inline badges surface fuzzy-merge proposals on the source (HL-CITE-12)", () => {
    const items: ReviewItem[] = [
      { id: "r1", item_type: "duplicate-merge-proposal", title: "dup", origin_id: "s-a", target_id: "s-b" },
      { id: "r2", item_type: "broken-link", title: "broken", origin_id: "c-1", target_id: "s-a" },
      { id: "r3", item_type: "note-recovery", title: "unrelated" },
    ];
    const badges = inlineBadgesForSource(items, "s-a");
    expect(badges.map((b) => b.kind).sort()).toEqual(["broken-link", "duplicate"]);
    expect(badges.find((b) => b.kind === "duplicate")?.reviewItemId).toBe("r1");
  });

  test("summary detects empty state and counts unsupported claims", () => {
    const claims: ClaimRecord[] = [
      { id: "c1", text: "a", status: "draft" },
      { id: "c2", text: "b", status: "supported" },
    ];
    const summary = summarizeCitationEvidence({ claims, citations: [], evidence: [] });
    expect(summary.unsupportedClaims).toBe(1);
    expect(summary.isEmpty).toBe(false);
    expect(summarizeCitationEvidence({ claims: [], citations: [], evidence: [] }).isEmpty).toBe(true);
  });
});
