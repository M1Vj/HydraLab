from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

import httpx


async def search_academic_sources(query: str) -> list[dict[str, Any]]:
    openalex = await _openalex(query)
    if openalex:
        return openalex
    return [_fallback_source(query)]


def compose_research_answer(query: str, sources: list[dict[str, Any]]) -> str:
    lead = sources[0]
    title = lead.get("title", "the retrieved source")
    abstract = lead.get("abstract") or "Hydra found a relevant source but no abstract was available."
    trimmed = re.sub(r"\s+", " ", abstract).strip()[:420]
    return f"Hydra found evidence relevant to '{query}'. {title} is the strongest current lead. {trimmed}"


def citation_for(query: str, source: dict[str, Any]) -> dict[str, str]:
    return {
        "source_id": source["id"],
        "claim": f"Evidence related to {query}",
        "quote": (source.get("abstract") or source.get("title") or "")[:240],
    }


async def _openalex(query: str) -> list[dict[str, Any]]:
    url = f"https://api.openalex.org/works?search={quote_plus(query)}&per-page=3"
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return []

    results = []
    for item in data.get("results", []):
        authors = ", ".join(
            author.get("author", {}).get("display_name", "")
            for author in item.get("authorships", [])[:4]
            if author.get("author", {}).get("display_name")
        )
        abstract = _abstract_from_inverted_index(item.get("abstract_inverted_index") or {})
        results.append(
            {
                "id": f"openalex_{str(item.get('id', '')).rsplit('/', 1)[-1] or len(results)}",
                "title": item.get("title") or "Untitled OpenAlex work",
                "authors": authors,
                "year": str(item.get("publication_year") or ""),
                "url": item.get("doi") or item.get("id") or "",
                "abstract": abstract,
                "kind": "article",
            }
        )
    return results


def _abstract_from_inverted_index(index: dict[str, list[int]]) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for position in positions:
            words.append((position, word))
    return " ".join(word for _, word in sorted(words))


def _fallback_source(query: str) -> dict[str, Any]:
    normalized = query.strip().title()
    return {
        "id": f"local_{re.sub(r'[^a-z0-9]+', '_', query.lower()).strip('_') or 'source'}",
        "title": f"Research lead for {normalized}",
        "authors": "Hydra local research index",
        "year": "",
        "url": "",
        "abstract": f"Local fallback source created for '{query}'. Connect academic providers for live OpenAlex, arXiv, and Unpaywall retrieval.",
        "kind": "article",
    }
