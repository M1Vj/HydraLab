"""Confidence-based duplicate detection (HL-CITE-04, Section 26.9/32.3).

- Exact identifier/hash match (same DOI, normalized arXiv id, canonical
  provider id, or file hash) => ``auto_merge`` eligible.
- High-confidence fuzzy (very similar title/authors/year, no shared id)
  => ``needs_review`` (never auto-merge).
- Otherwise => ``flagged`` (kept separate) or ``none``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Optional

FUZZY_REVIEW_THRESHOLD = 0.82
FUZZY_FLAG_THRESHOLD = 0.6


@dataclass
class DuplicateVerdict:
    status: str  # auto_merge | needs_review | flagged | none
    confidence: float
    reason: str  # exact_identifier | exact_hash | fuzzy_title | none


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _norm_arxiv(value: Any) -> str:
    raw = str(value or "").lower().strip()
    raw = re.sub(r"^arxiv[:_/]?", "", raw)
    raw = re.sub(r"v\d+$", "", raw)
    return _norm(raw)


def _identifiers(source: dict[str, Any]) -> dict[str, str]:
    ids: dict[str, str] = {}
    if source.get("doi"):
        ids["doi"] = _norm(source["doi"])
    if source.get("arxiv_id"):
        ids["arxiv"] = _norm_arxiv(source["arxiv_id"])
    extra = source.get("identifiers")
    if isinstance(extra, dict):
        for key, value in extra.items():
            if value:
                ids[str(key)] = _norm(value)
    for key in ("file_hash", "content_hash"):
        if source.get(key):
            ids[key] = _norm(source[key])
    return ids


def _title_year_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_title = _norm(left.get("title"))
    right_title = _norm(right.get("title"))
    if not left_title or not right_title:
        return 0.0
    ratio = SequenceMatcher(None, left_title, right_title).ratio()
    left_year = _norm(left.get("year"))
    right_year = _norm(right.get("year"))
    if left_year and right_year and left_year == right_year:
        ratio = min(1.0, ratio + 0.05)
    elif left_year and right_year and left_year != right_year:
        ratio = max(0.0, ratio - 0.1)
    return ratio


def classify_pair(left: dict[str, Any], right: dict[str, Any]) -> DuplicateVerdict:
    left_ids = _identifiers(left)
    right_ids = _identifiers(right)
    for key, value in left_ids.items():
        if value and right_ids.get(key) == value:
            reason = "exact_hash" if key in {"file_hash", "content_hash"} else "exact_identifier"
            return DuplicateVerdict(status="auto_merge", confidence=1.0, reason=reason)

    similarity = _title_year_similarity(left, right)
    if similarity >= FUZZY_REVIEW_THRESHOLD:
        return DuplicateVerdict(status="needs_review", confidence=round(similarity, 3), reason="fuzzy_title")
    if similarity >= FUZZY_FLAG_THRESHOLD:
        return DuplicateVerdict(status="flagged", confidence=round(similarity, 3), reason="fuzzy_title")
    return DuplicateVerdict(status="none", confidence=round(similarity, 3), reason="none")


def find_duplicates(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pairwise scan returning non-``none`` verdicts among live sources."""
    live = [s for s in sources if not s.get("trashed") and not s.get("merged_into_source_id")]
    results: list[dict[str, Any]] = []
    for i in range(len(live)):
        for j in range(i + 1, len(live)):
            verdict = classify_pair(live[i], live[j])
            if verdict.status != "none":
                results.append(
                    {
                        "left_id": live[i]["id"],
                        "right_id": live[j]["id"],
                        "status": verdict.status,
                        "confidence": verdict.confidence,
                        "reason": verdict.reason,
                    }
                )
    return results
