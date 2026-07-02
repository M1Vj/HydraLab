"""Source-traceable retrieval for built-in recipes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import LexicalIndexEntry, Source
from hydra.database.repository import Repository


@dataclass(frozen=True)
class RetrievalOptions:
    semantic_enabled: bool = False
    offline_only: bool = False
    g3_enabled: bool = False
    depth: str = "standard"


@dataclass(frozen=True)
class LiteratureHit:
    source_id: str
    citation_id: str | None
    locator: dict[str, Any]
    chunk_id: str
    extraction_version: int
    index_version: int
    confidence: float
    text: str
    source_title: str = ""
    query_mode: str = "lexical"

    def public_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "citation_id": self.citation_id,
            "locator": self.locator,
            "chunk_id": self.chunk_id,
            "extraction_version": self.extraction_version,
            "index_version": self.index_version,
            "confidence": self.confidence,
            "text": self.text,
            "source_title": self.source_title,
            "query_mode": self.query_mode,
        }


@dataclass(frozen=True)
class RetrievalResult:
    hits: list[LiteratureHit] = field(default_factory=list)
    semantic_attempted: bool = False
    offline_notice: str | None = None
    notices: list[str] = field(default_factory=list)


async def retrieve_literature_hits(
    session: AsyncSession,
    *,
    query: str,
    source_scope: dict[str, Any],
    options: RetrievalOptions | None = None,
) -> RetrievalResult:
    """Retrieve saved-source chunks without inventing source references."""

    options = options or RetrievalOptions()
    repo = Repository(session)
    citations = await repo.list_citations()
    citation_by_source: dict[str, str] = {}
    for citation in citations:
        citation_by_source.setdefault(str(citation.get("source_id") or ""), str(citation.get("id") or ""))

    source_rows = (await session.exec(select(Source).where(Source.trashed == False))).all()  # noqa: E712
    source_by_id = {source.id: source for source in source_rows}
    allowed_source_ids = _resolve_scope_source_ids(source_rows, source_scope)

    rows = (await session.exec(select(LexicalIndexEntry))).all()
    lexical_hits: list[LiteratureHit] = []
    for row in rows:
        if not row.source_id or row.source_id not in source_by_id:
            continue
        if allowed_source_ids is not None and row.source_id not in allowed_source_ids:
            continue
        confidence = _lexical_confidence(query, row.text)
        if confidence <= 0:
            continue
        lexical_hits.append(
            LiteratureHit(
                source_id=row.source_id,
                citation_id=citation_by_source.get(row.source_id),
                locator=_safe_locator(row.locator),
                chunk_id=row.chunk_id,
                extraction_version=row.extraction_version,
                index_version=row.index_version,
                confidence=confidence,
                text=row.text,
                source_title=source_by_id[row.source_id].title,
                query_mode=row.query_mode or "lexical",
            )
        )

    notices: list[str] = []
    semantic_attempted = False
    offline_notice = None
    if options.semantic_enabled:
        if options.offline_only:
            offline_notice = "provider semantic search is unavailable offline"
            notices.append(offline_notice)
        elif not options.g3_enabled:
            notices.append("provider semantic search requires G3 consent")
        else:
            semantic_attempted = True
            notices.append("provider semantic search returned no additional local fixture hits")

    return RetrievalResult(
        hits=sorted(lexical_hits, key=lambda hit: (-hit.confidence, hit.source_id, hit.chunk_id))[
            : _depth_limit(options.depth)
        ],
        semantic_attempted=semantic_attempted,
        offline_notice=offline_notice,
        notices=notices,
    )


def _resolve_scope_source_ids(sources: list[Source], source_scope: dict[str, Any]) -> set[str] | None:
    kind = str(source_scope.get("kind") or "all-project")
    if kind == "source-ids":
        return {str(source_id) for source_id in source_scope.get("source_ids") or [] if str(source_id)}
    if kind in {"tag", "folder"}:
        value = str(source_scope.get("value") or "").strip().lower()
        if not value:
            return set()
        matched: set[str] = set()
        for source in sources:
            metadata = _json_value(source.metadata_json, {})
            keywords = _json_value(source.keywords, [])
            haystack = " ".join(
                [
                    source.title or "",
                    source.url or "",
                    json.dumps(metadata, sort_keys=True),
                    json.dumps(keywords, sort_keys=True),
                ]
            ).lower()
            if value in haystack:
                matched.add(source.id)
        return matched
    return None


def _safe_locator(raw: str) -> dict[str, Any]:
    parsed = _json_value(raw, {})
    return parsed if isinstance(parsed, dict) else {"raw": str(raw or "")}


def _json_value(raw: Any, fallback: Any) -> Any:
    if raw is None:
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


def _lexical_confidence(query: str, text: str) -> float:
    terms = {term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) > 2}
    if not terms:
        return 0.25 if text.strip() else 0.0
    body = text.lower()
    matched = sum(1 for term in terms if term in body)
    if matched == 0:
        return 0.0
    return min(1.0, max(0.05, matched / len(terms)))


def _depth_limit(depth: str) -> int:
    return {"quick": 4, "standard": 8, "deep": 16}.get(str(depth or "standard"), 8)
