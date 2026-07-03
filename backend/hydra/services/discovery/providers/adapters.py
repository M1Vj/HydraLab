from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import httpx

from hydra.services.discovery.base import DiscoveryResult, SourceProviderConfig, now_iso, provider_headers


class HttpJsonProvider:
    name = "provider"
    search_url = ""

    async def search(self, query: str, config: SourceProviderConfig) -> list[DiscoveryResult]:
        if not self.search_url:
            return []
        url = self.search_url.format(query=quote_plus(query), email=quote_plus(config.contact_email))
        async with httpx.AsyncClient(timeout=config.timeout_seconds, headers=provider_headers(self.name, config)) as client:
            response = await client.get(url)
            if response.status_code == 429:
                from hydra.services.discovery.limiter import RateLimitExceeded

                raise RateLimitExceeded(self.name)
            response.raise_for_status()
            payload = response.json()
        return [item.with_query(query) for item in self.normalize(payload, response.status_code)]

    async def fetch_by_id(self, identifier: str, config: SourceProviderConfig) -> DiscoveryResult | None:
        results = await self.search(identifier, config)
        return results[0] if results else None

    def normalize(self, payload: dict[str, Any], status: int = 200) -> list[DiscoveryResult]:
        return []


class OpenAlexProvider(HttpJsonProvider):
    name = "openalex"
    search_url = "https://api.openalex.org/works?search={query}&per-page=5"

    def normalize(self, payload: dict[str, Any], status: int = 200) -> list[DiscoveryResult]:
        results = []
        for item in payload.get("results", []):
            authors = [
                author.get("author", {}).get("display_name", "")
                for author in item.get("authorships", [])[:6]
                if author.get("author", {}).get("display_name")
            ]
            open_access = item.get("open_access") or {}
            primary = item.get("primary_location") or {}
            results.append(
                DiscoveryResult(
                    title=item.get("title") or "Untitled OpenAlex work",
                    authors=authors,
                    year=item.get("publication_year"),
                    venue=(primary.get("source") or {}).get("display_name") or "",
                    doi=item.get("doi"),
                    arxiv_id=None,
                    openalex_id=str(item.get("id") or "").rsplit("/", 1)[-1] or None,
                    s2_id=None,
                    url=item.get("doi") or item.get("id"),
                    pdf_available=bool(open_access.get("is_oa")),
                    pdf_url=open_access.get("oa_url"),
                    expected_size_bytes=None,
                    provider=self.name,
                    retrieved_at=now_iso(),
                    response_status=status,
                    confidence=0.82,
                    abstract="",
                )
            )
        return results


class CrossrefProvider(HttpJsonProvider):
    name = "crossref"
    search_url = "https://api.crossref.org/works?query={query}&rows=5&mailto={email}"

    def normalize(self, payload: dict[str, Any], status: int = 200) -> list[DiscoveryResult]:
        results = []
        for item in (payload.get("message") or {}).get("items", []):
            title = (item.get("title") or ["Untitled Crossref work"])[0]
            authors = [
                " ".join(part for part in (author.get("given"), author.get("family")) if part)
                for author in item.get("author", [])[:6]
            ]
            year_parts = ((item.get("published-print") or item.get("published-online") or item.get("issued") or {}).get("date-parts") or [[None]])[0]
            year = year_parts[0] if year_parts else None
            links = item.get("link") or []
            pdf = next((link for link in links if "pdf" in str(link.get("content-type", "")).lower()), {})
            results.append(
                DiscoveryResult(
                    title=title,
                    authors=[author for author in authors if author],
                    year=year,
                    venue=(item.get("container-title") or [""])[0],
                    doi=item.get("DOI"),
                    arxiv_id=None,
                    openalex_id=None,
                    s2_id=None,
                    url=item.get("URL") or (f"https://doi.org/{item.get('DOI')}" if item.get("DOI") else None),
                    pdf_available=bool(pdf.get("URL")),
                    pdf_url=pdf.get("URL"),
                    expected_size_bytes=None,
                    provider=self.name,
                    retrieved_at=now_iso(),
                    response_status=status,
                    confidence=0.78,
                    abstract=item.get("abstract") or "",
                )
            )
        return results


class ArxivProvider(HttpJsonProvider):
    name = "arxiv"
    search_url = ""

    async def search(self, query: str, config: SourceProviderConfig) -> list[DiscoveryResult]:
        from hydra.research import _arxiv

        raw = await _arxiv(query)
        return [
            DiscoveryResult(
                title=item["title"],
                authors=[author.strip() for author in item.get("authors", "").split(",") if author.strip()],
                year=int(item["year"]) if item.get("year") else None,
                venue="arXiv",
                doi=None,
                arxiv_id=str(item["id"]).removeprefix("arxiv_"),
                openalex_id=None,
                s2_id=None,
                url=item.get("url"),
                pdf_available=True,
                pdf_url=(item.get("url") or "").replace("/abs/", "/pdf/"),
                expected_size_bytes=None,
                provider=self.name,
                retrieved_at=now_iso(),
                response_status=200,
                confidence=0.8,
                abstract=item.get("abstract", ""),
                query=query,
            )
            for item in raw
        ]


class UnpaywallProvider(HttpJsonProvider):
    name = "unpaywall"
    search_url = "https://api.unpaywall.org/v2/search/?query={query}&email={email}"

    def normalize(self, payload: dict[str, Any], status: int = 200) -> list[DiscoveryResult]:
        results = []
        for wrapper in payload.get("results", []):
            item = wrapper.get("response") or wrapper
            location = item.get("best_oa_location") or {}
            authors = [
                " ".join(part for part in (author.get("given"), author.get("family")) if part)
                for author in item.get("z_authors", [])[:6]
            ]
            results.append(
                DiscoveryResult(
                    title=item.get("title") or "Untitled Unpaywall work",
                    authors=[author for author in authors if author],
                    year=item.get("year"),
                    venue=item.get("journal_name") or "",
                    doi=item.get("doi"),
                    arxiv_id=None,
                    openalex_id=None,
                    s2_id=None,
                    url=location.get("url") or (f"https://doi.org/{item.get('doi')}" if item.get("doi") else None),
                    pdf_available=bool(location.get("url_for_pdf")),
                    pdf_url=location.get("url_for_pdf"),
                    expected_size_bytes=None,
                    provider=self.name,
                    retrieved_at=now_iso(),
                    response_status=status,
                    confidence=float(wrapper.get("score") or 0.72),
                )
            )
        return results


class SemanticScholarProvider(HttpJsonProvider):
    name = "semantic_scholar"
    search_url = "https://api.semanticscholar.org/graph/v1/paper/search?query={query}&limit=5&fields=title,authors,year,venue,externalIds,openAccessPdf,url"

    def normalize(self, payload: dict[str, Any], status: int = 200) -> list[DiscoveryResult]:
        results = []
        for item in payload.get("data", []):
            external = item.get("externalIds") or {}
            pdf = item.get("openAccessPdf") or {}
            results.append(
                DiscoveryResult(
                    title=item.get("title") or "Untitled Semantic Scholar paper",
                    authors=[author.get("name", "") for author in item.get("authors", [])[:6] if author.get("name")],
                    year=item.get("year"),
                    venue=item.get("venue") or "",
                    doi=external.get("DOI"),
                    arxiv_id=external.get("ArXiv"),
                    openalex_id=external.get("OpenAlex"),
                    s2_id=item.get("paperId"),
                    url=item.get("url"),
                    pdf_available=bool(pdf.get("url")),
                    pdf_url=pdf.get("url"),
                    expected_size_bytes=None,
                    provider=self.name,
                    retrieved_at=now_iso(),
                    response_status=status,
                    confidence=0.8,
                )
            )
        return results


class CoreProvider(HttpJsonProvider):
    name = "core"
    search_url = "https://api.core.ac.uk/v3/search/works?q={query}&limit=5"

    def normalize(self, payload: dict[str, Any], status: int = 200) -> list[DiscoveryResult]:
        results = []
        for item in payload.get("results", []):
            download = item.get("downloadUrl")
            journals = item.get("journals") or []
            journal_title = journals[0].get("title", "") if journals and isinstance(journals[0], dict) else ""
            results.append(
                DiscoveryResult(
                    title=item.get("title") or "Untitled CORE work",
                    authors=[author.get("name", author) if isinstance(author, dict) else str(author) for author in item.get("authors", [])[:6]],
                    year=item.get("yearPublished"),
                    venue=item.get("publisher") or journal_title,
                    doi=item.get("doi"),
                    arxiv_id=None,
                    openalex_id=None,
                    s2_id=None,
                    url=item.get("sourceFulltextUrls", [None])[0] if item.get("sourceFulltextUrls") else item.get("url"),
                    pdf_available=bool(download),
                    pdf_url=download,
                    expected_size_bytes=None,
                    provider=self.name,
                    retrieved_at=now_iso(),
                    response_status=status,
                    confidence=0.7,
                    abstract=item.get("abstract") or "",
                )
            )
        return results


class OpenCitationsProvider(HttpJsonProvider):
    name = "opencitations"
    search_url = "https://api.opencitations.net/meta/api/v1/metadata/{query}"

    def normalize(self, payload: dict[str, Any] | list[dict[str, Any]], status: int = 200) -> list[DiscoveryResult]:
        items = payload if isinstance(payload, list) else payload.get("results", [])
        results = []
        for item in items:
            results.append(
                DiscoveryResult(
                    title=item.get("title") or "Untitled OpenCitations record",
                    authors=[part.strip() for part in str(item.get("author") or "").split(";") if part.strip()],
                    year=int(str(item.get("pub_date") or "")[:4]) if str(item.get("pub_date") or "")[:4].isdigit() else None,
                    venue=item.get("venue") or "",
                    doi=item.get("doi"),
                    arxiv_id=None,
                    openalex_id=None,
                    s2_id=None,
                    url=f"https://doi.org/{item['doi']}" if item.get("doi") else None,
                    pdf_available=False,
                    pdf_url=None,
                    expected_size_bytes=None,
                    provider=self.name,
                    retrieved_at=now_iso(),
                    response_status=status,
                    confidence=0.68,
                )
            )
        return results


def default_providers() -> list[HttpJsonProvider]:
    return [
        OpenAlexProvider(),
        ArxivProvider(),
        CrossrefProvider(),
        UnpaywallProvider(),
        SemanticScholarProvider(),
        CoreProvider(),
        OpenCitationsProvider(),
    ]
