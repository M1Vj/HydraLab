from __future__ import annotations

import difflib
from dataclasses import replace
from typing import Any

from hydra.services.discovery.base import DiscoveryResult, author_string


def dedupe_discovery_results(
    results: list[DiscoveryResult],
    existing_sources: list[dict[str, Any]],
) -> tuple[list[DiscoveryResult], list[dict[str, Any]]]:
    merged: dict[str, DiscoveryResult] = {}
    no_exact: list[DiscoveryResult] = []
    for result in sorted(results, key=lambda item: item.confidence, reverse=True):
        exact_key = result.exact_key()
        if exact_key:
            existing = merged.get(exact_key)
            if existing:
                sources = tuple(existing.metadata_sources or (existing,)) + (result,)
                best = result if result.confidence >= existing.confidence else existing
                merged[exact_key] = replace(best, metadata_sources=sources, duplicate_state="exact-merged")
            else:
                merged[exact_key] = replace(result, metadata_sources=(result,))
        else:
            no_exact.append(result)

    review_items: list[dict[str, Any]] = []
    deduped = list(merged.values())
    for result in no_exact:
        fuzzy_existing = _find_fuzzy_existing(result, existing_sources)
        if fuzzy_existing:
            deduped.append(replace(result, duplicate_state="fuzzy-review"))
            review_items.append(
                {
                    "item_type": "duplicate-candidate",
                    "title": f"Review possible duplicate: {result.title}",
                    "summary": "High-confidence title/author/year match needs user decision before merge.",
                    "origin_type": "source-discovery",
                    "target_type": "source",
                    "payload": {
                        "candidate": result.to_dict(),
                        "existing_source": fuzzy_existing,
                    },
                }
            )
            continue
        if any(_title_similarity(result.title, other.title) >= 0.64 for other in deduped):
            deduped.append(replace(result, duplicate_state="possible-duplicate"))
        else:
            deduped.append(result)

    return sorted(deduped, key=lambda item: item.confidence, reverse=True), review_items


def _find_fuzzy_existing(result: DiscoveryResult, existing_sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    for source in existing_sources:
        same_year = str(source.get("year") or "") == str(result.year or "")
        if not same_year:
            continue
        title_score = _title_similarity(result.title, str(source.get("title") or ""))
        author_score = _title_similarity(author_string(result.authors), str(source.get("authors") or ""))
        if title_score >= 0.92 and author_score >= 0.45:
            return source
    return None


def _title_similarity(left: str, right: str) -> float:
    return difflib.SequenceMatcher(None, left.lower().strip(), right.lower().strip()).ratio()
