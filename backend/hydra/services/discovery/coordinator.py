from __future__ import annotations

import asyncio
from typing import Any

from hydra.services.discovery.base import DiscoveryResult, SourceProvider, SourceProviderConfig
from hydra.services.discovery.cache import DiscoveryCache
from hydra.services.discovery.dedupe import dedupe_discovery_results
from hydra.services.discovery.limiter import ProviderRateLimiter, RateLimitExceeded


class DiscoveryCoordinator:
    def __init__(
        self,
        *,
        providers: list[SourceProvider],
        cache: DiscoveryCache | None = None,
        limiter: ProviderRateLimiter | None = None,
        config: SourceProviderConfig | None = None,
    ):
        self.providers = providers
        self.cache = cache or DiscoveryCache()
        self.limiter = limiter or ProviderRateLimiter()
        self.config = config or SourceProviderConfig()

    def search_sync(
        self,
        query: str,
        *,
        offline_only: bool = False,
        scholarly_apis_enabled: bool = True,
        existing_sources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return asyncio.run(self.search(query, offline_only=offline_only, scholarly_apis_enabled=scholarly_apis_enabled, existing_sources=existing_sources or []))

    async def search(
        self,
        query: str,
        *,
        offline_only: bool = False,
        scholarly_apis_enabled: bool = True,
        existing_sources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        results: list[DiscoveryResult] = []
        statuses: list[dict[str, Any]] = []
        any_cache_hit = False
        existing_sources = existing_sources or []

        async def run_provider(provider: SourceProvider) -> None:
            nonlocal any_cache_hit
            cached, age = self.cache.get_query(provider.name, query)
            if cached is not None:
                any_cache_hit = True
                results.extend(cached)
                statuses.append({"provider": provider.name, "state": "cache-hit", "cache_age_seconds": age})
                return
            if offline_only or not scholarly_apis_enabled:
                statuses.append({"provider": provider.name, "state": "offline"})
                return
            try:
                provider_results = await self.limiter.call(provider.name, lambda: provider.search(query, self.config))
                self.cache.set_query(provider.name, query, provider_results)
                results.extend(provider_results)
                statuses.append({"provider": provider.name, "state": "ready", "count": len(provider_results)})
            except RateLimitExceeded:
                statuses.append({"provider": provider.name, "state": "provider rate-limited"})
            except Exception as exc:
                statuses.append({"provider": provider.name, "state": "error", "error": exc.__class__.__name__})

        await asyncio.gather(*(run_provider(provider) for provider in self.providers))
        deduped, review_items = dedupe_discovery_results(results, existing_sources)
        if offline_only or not scholarly_apis_enabled:
            state = "offline-permission"
        elif results and any(status["state"] in {"error", "provider rate-limited"} for status in statuses):
            state = "partial"
        elif results:
            state = "ready"
        elif statuses and all(status["state"] in {"error", "provider rate-limited"} for status in statuses):
            state = "failure"
        else:
            state = "empty"

        return {
            "query": query,
            "state": state,
            "cache_hit": any_cache_hit,
            "provider_statuses": sorted(statuses, key=lambda status: status["provider"]),
            "results": [result.to_dict() for result in deduped],
            "review_items": review_items,
        }

    def refresh_sync(self, identifier: str, query: str) -> dict[str, Any]:
        return asyncio.run(self.refresh(identifier, query))

    async def refresh(self, identifier: str, query: str) -> dict[str, Any]:
        for provider in self.providers:
            result = await self.limiter.call(provider.name, lambda provider=provider: provider.fetch_by_id(identifier, self.config))
            if result is not None:
                result = result.with_query(query)
                self.cache.set_query(provider.name, query, [result])
                return {"result": result.to_dict(), "cache_age_seconds": 0}
        return {"result": None, "cache_age_seconds": None}
