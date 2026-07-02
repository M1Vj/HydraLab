from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlparse

TRUST_LEVEL_UNTRUSTED = "untrusted-external"
USER_AGENT = "HydraLab/0.1 (local-first research workbench; mailto:{email})"
LARGE_FILE_THRESHOLD_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class SourceProviderConfig:
    contact_email: str = "research@hydralab.local"
    api_keys: dict[str, str] = field(default_factory=dict)
    secret_refs: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 8.0


@dataclass(frozen=True)
class DiscoveryResult:
    title: str
    authors: list[str]
    year: int | None
    venue: str
    doi: str | None
    arxiv_id: str | None
    openalex_id: str | None
    s2_id: str | None
    url: str | None
    pdf_available: bool
    pdf_url: str | None
    expected_size_bytes: int | None
    provider: str
    retrieved_at: str
    response_status: int
    confidence: float
    trust_level: str = TRUST_LEVEL_UNTRUSTED
    query: str = ""
    source_id: str | None = None
    duplicate_state: str = "unique"
    metadata_sources: tuple["DiscoveryResult", ...] = field(default_factory=tuple, compare=False)
    abstract: str = ""

    def __post_init__(self) -> None:
        if self.trust_level != TRUST_LEVEL_UNTRUSTED:
            raise ValueError("discovery metadata must be untrusted-external until user save")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

    @property
    def id(self) -> str:
        if self.source_id:
            return self.source_id
        key = self.exact_key() or self.url or f"{self.provider}:{self.title}:{self.year or ''}"
        return "disc_" + hashlib.sha256(key.lower().encode("utf-8")).hexdigest()[:16]

    def with_query(self, query: str) -> "DiscoveryResult":
        return replace(self, query=query)

    def exact_key(self) -> str | None:
        for prefix, value in (
            ("doi", self.doi),
            ("arxiv", self.arxiv_id),
            ("openalex", self.openalex_id),
            ("s2", self.s2_id),
            ("url", self.url),
        ):
            normalized = normalize_identifier(value)
            if normalized:
                return f"{prefix}:{normalized}"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "authors": list(self.authors),
            "year": self.year,
            "venue": self.venue,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "openalex_id": self.openalex_id,
            "s2_id": self.s2_id,
            "url": self.url,
            "pdf_available": self.pdf_available,
            "pdf_url": self.pdf_url,
            "expected_size_bytes": self.expected_size_bytes,
            "provider": self.provider,
            "retrieved_at": self.retrieved_at,
            "response_status": self.response_status,
            "confidence": self.confidence,
            "trust_level": self.trust_level,
            "query": self.query,
            "duplicate_state": self.duplicate_state,
            "metadata_sources": [
                source.to_provenance_dict(query=self.query)
                for source in (self.metadata_sources or (self,))
            ],
            "abstract": self.abstract,
        }

    def to_provenance_dict(self, query: str | None = None) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "query": query if query is not None else self.query,
            "retrieved_at": self.retrieved_at,
            "response_status": self.response_status,
            "confidence": self.confidence,
        }


class SourceProvider(Protocol):
    name: str

    async def search(self, query: str, config: SourceProviderConfig) -> list[DiscoveryResult]:
        ...

    async def fetch_by_id(self, identifier: str, config: SourceProviderConfig) -> DiscoveryResult | None:
        ...


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_identifier(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    normalized = re.sub(r"^https?://(dx\.)?doi\.org/", "", normalized, flags=re.I)
    normalized = re.sub(r"^https?://openalex\.org/", "", normalized, flags=re.I)
    normalized = normalized.removeprefix("arXiv:")
    normalized = re.sub(r"v\d+$", "", normalized)
    normalized = normalized.strip().lower()
    return normalized or None


def query_hash(query: str) -> str:
    return hashlib.sha256(" ".join(query.lower().split()).encode("utf-8")).hexdigest()


def author_string(authors: list[str]) -> str:
    return "; ".join(author.strip() for author in authors if author.strip())


def provider_headers(provider: str, config: SourceProviderConfig) -> dict[str, str]:
    email = config.contact_email or "research@hydralab.local"
    headers = {"User-Agent": USER_AGENT.format(email=email)}
    if provider == "crossref":
        headers["mailto"] = email
    key = config.api_keys.get(provider)
    if key:
        if provider == "semantic_scholar":
            headers["x-api-key"] = key
        elif provider == "core":
            headers["Authorization"] = f"Bearer {key}"
        else:
            headers["Authorization"] = f"Bearer {key}"
    return headers


def evaluate_pdf_download_policy(
    *,
    pdf_url: str | None,
    expected_size_bytes: int | None,
    automatic_download: bool,
    explicit_save_with_pdf: bool,
    allowed_domains: list[str],
    size_limit_bytes: int = LARGE_FILE_THRESHOLD_BYTES,
    storage_remaining_bytes: int | None = None,
) -> dict[str, Any]:
    if not pdf_url:
        return {"download": False, "reason": "no-open-access-pdf"}
    host = urlparse(pdf_url).hostname or ""
    if allowed_domains and not any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains):
        return {"download": False, "reason": "domain-not-allowlisted"}
    if expected_size_bytes is not None and expected_size_bytes > size_limit_bytes:
        return {"download": False, "reason": "over-size-limit"}
    if storage_remaining_bytes is not None and expected_size_bytes is not None and expected_size_bytes > storage_remaining_bytes:
        return {"download": False, "reason": "storage-limit"}
    if explicit_save_with_pdf:
        return {"download": True, "reason": "explicit-save"}
    if automatic_download:
        return {"download": True, "reason": "automatic-open-access"}
    return {"download": False, "reason": "explicit-save-required"}


def result_from_dict(data: dict[str, Any]) -> DiscoveryResult:
    return DiscoveryResult(
        title=str(data.get("title") or "Untitled source"),
        authors=list(data.get("authors") or []),
        year=data.get("year"),
        venue=str(data.get("venue") or ""),
        doi=data.get("doi"),
        arxiv_id=data.get("arxiv_id"),
        openalex_id=data.get("openalex_id"),
        s2_id=data.get("s2_id"),
        url=data.get("url"),
        pdf_available=bool(data.get("pdf_available")),
        pdf_url=data.get("pdf_url"),
        expected_size_bytes=data.get("expected_size_bytes"),
        provider=str(data.get("provider") or "unknown"),
        retrieved_at=str(data.get("retrieved_at") or now_iso()),
        response_status=int(data.get("response_status") or 200),
        confidence=float(data.get("confidence") or 0.5),
        trust_level=str(data.get("trust_level") or TRUST_LEVEL_UNTRUSTED),
        query=str(data.get("query") or ""),
        duplicate_state=str(data.get("duplicate_state") or "unique"),
        abstract=str(data.get("abstract") or ""),
    )
