from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus

import httpx


async def search_academic_sources(query: str) -> list[dict[str, Any]]:
    results = []
    results.extend(await _openalex(query))
    results.extend(await _arxiv(query))
    if results:
        dois = [source["url"].removeprefix("https://doi.org/") for source in results if source.get("url", "").startswith("https://doi.org/")]
        results.extend(await _unpaywall(dois[:2]))
    deduped = _dedupe_sources(results)
    if deduped:
        return deduped[:6]
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
        results.append(normalize_openalex_work(item))
    return results


async def _arxiv(query: str) -> list[dict[str, Any]]:
    url = f"https://export.arxiv.org/api/query?search_query=all:{quote_plus(query)}&start=0&max_results=3"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(url)
            response.raise_for_status()
            root = ET.fromstring(response.text)
    except Exception:
        return []

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    results = []
    for entry in root.findall("atom:entry", namespace):
        source = {
            "id": _text(entry.find("atom:id", namespace)).rsplit("/", 1)[-1],
            "title": _text(entry.find("atom:title", namespace)),
            "authors": [_text(author.find("atom:name", namespace)) for author in entry.findall("atom:author", namespace)],
            "published": _text(entry.find("atom:published", namespace)),
            "summary": _text(entry.find("atom:summary", namespace)),
            "url": _text(entry.find("atom:id", namespace)),
        }
        results.append(normalize_arxiv_entry(source))
    return results


async def _unpaywall(dois: list[str]) -> list[dict[str, Any]]:
    results = []
    for doi in dois:
        url = f"https://api.unpaywall.org/v2/{quote_plus(doi)}?email=hydra@example.invalid"
        try:
            async with httpx.AsyncClient(timeout=4) as client:
                response = await client.get(url)
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                results.append(normalize_unpaywall_work(response.json()))
        except Exception:
            continue
    return results


def normalize_openalex_work(item: dict[str, Any]) -> dict[str, Any]:
    authors = ", ".join(
        author.get("author", {}).get("display_name", "")
        for author in item.get("authorships", [])[:4]
        if author.get("author", {}).get("display_name")
    )
    work_id = str(item.get("id", "")).rsplit("/", 1)[-1] or "work"
    return {
        "id": f"openalex_{work_id}",
        "title": item.get("title") or "Untitled OpenAlex work",
        "authors": authors,
        "year": str(item.get("publication_year") or ""),
        "url": item.get("doi") or item.get("id") or "",
        "abstract": _abstract_from_inverted_index(item.get("abstract_inverted_index") or {}),
        "kind": "article",
    }


def normalize_arxiv_entry(entry: dict[str, Any]) -> dict[str, Any]:
    raw_id = str(entry.get("id") or "").rsplit("/", 1)[-1]
    stable_id = re.sub(r"v\d+$", "", raw_id)
    return {
        "id": f"arxiv_{stable_id}",
        "title": _clean_text(str(entry.get("title") or "Untitled arXiv preprint")),
        "authors": ", ".join(entry.get("authors") or []),
        "year": str(entry.get("published") or "")[:4],
        "url": entry.get("url") or f"https://arxiv.org/abs/{stable_id}",
        "abstract": _clean_text(str(entry.get("summary") or "")),
        "kind": "preprint",
    }


def normalize_unpaywall_work(item: dict[str, Any]) -> dict[str, Any]:
    doi = str(item.get("doi") or "").lower()
    authors = ", ".join(
        " ".join(part for part in (author.get("given"), author.get("family")) if part)
        for author in item.get("z_authors", [])[:4]
    )
    location = item.get("best_oa_location") or {}
    return {
        "id": f"unpaywall_{re.sub(r'[^a-z0-9]+', '_', doi).strip('_')}",
        "title": item.get("title") or "Untitled open-access work",
        "authors": authors,
        "year": str(item.get("year") or ""),
        "url": location.get("url_for_pdf") or location.get("url") or (f"https://doi.org/{doi}" if doi else ""),
        "abstract": "",
        "kind": "open_access",
    }


def _abstract_from_inverted_index(index: dict[str, list[int]]) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for position in positions:
            words.append((position, word))
    return " ".join(word for _, word in sorted(words))


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for source in sources:
        key = source.get("url") or source.get("id") or source.get("title")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _text(element: ET.Element | None) -> str:
    return "" if element is None or element.text is None else element.text.strip()


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


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
