from __future__ import annotations

import time
from dataclasses import dataclass

from hydra.services.discovery.base import DiscoveryResult, query_hash


@dataclass
class CacheEntry:
    results: list[DiscoveryResult]
    created_at: float


class DiscoveryCache:
    def __init__(self, ttl_seconds: int = 24 * 60 * 60):
        self.ttl_seconds = ttl_seconds
        self._query_entries: dict[str, CacheEntry] = {}
        self._result_entries: dict[str, CacheEntry] = {}

    def query_key(self, provider: str, query: str) -> str:
        return f"{provider}:query:{query_hash(query)}"

    def get_query(self, provider: str, query: str) -> tuple[list[DiscoveryResult] | None, int | None]:
        entry = self._query_entries.get(self.query_key(provider, query))
        if not entry:
            return None, None
        age = int(time.time() - entry.created_at)
        if age > self.ttl_seconds:
            return None, age
        return entry.results, age

    def set_query(self, provider: str, query: str, results: list[DiscoveryResult]) -> None:
        now = time.time()
        self._query_entries[self.query_key(provider, query)] = CacheEntry(results=results, created_at=now)
        for result in results:
            self._result_entries[result.id] = CacheEntry(results=[result], created_at=now)
            for exact in filter(None, [result.doi, result.arxiv_id, result.openalex_id, result.s2_id, result.url]):
                self._result_entries[f"{provider}:id:{exact}".lower()] = CacheEntry(results=[result], created_at=now)

    def get_result(self, identifier: str) -> tuple[DiscoveryResult | None, int | None]:
        entry = self._result_entries.get(identifier) or self._result_entries.get(identifier.lower())
        if not entry:
            return None, None
        age = int(time.time() - entry.created_at)
        if age > self.ttl_seconds:
            return None, age
        return entry.results[0], age

    def clear(self) -> None:
        self._query_entries.clear()
        self._result_entries.clear()
