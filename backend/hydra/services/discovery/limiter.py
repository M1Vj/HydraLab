from __future__ import annotations

import time
import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class RateLimitExceeded(Exception):
    def __init__(self, provider: str):
        super().__init__(provider)
        self.provider = provider


class ProviderRateLimiter:
    def __init__(
        self,
        *,
        aggregate_requests_per_second: int = 3,
        max_retries: int = 3,
        base_delay_seconds: float = 0.25,
        provider_requests_per_second: dict[str, float] | None = None,
    ):
        self.aggregate_requests_per_second = aggregate_requests_per_second
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self.provider_requests_per_second = provider_requests_per_second or {}
        self._recent_requests: deque[float] = deque()
        self._provider_recent_requests: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def wait_for_slot(self, provider: str) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                provider_recent = self._provider_recent_requests.setdefault(provider, deque())
                _prune(self._recent_requests, now)
                _prune(provider_recent, now)
                waits = []
                if len(self._recent_requests) >= self.aggregate_requests_per_second:
                    waits.append(max(0, 1 - (now - self._recent_requests[0])))
                provider_limit = self.provider_requests_per_second.get(provider)
                if provider_limit and len(provider_recent) >= provider_limit:
                    waits.append(max(0, 1 - (now - provider_recent[0])))
                if not waits:
                    self._recent_requests.append(now)
                    provider_recent.append(now)
                    return
                sleep_for = max(waits)
            await asyncio.sleep(sleep_for)

    async def call(self, provider: str, operation: Callable[[], Awaitable[T]]) -> T:
        last_error: RateLimitExceeded | None = None
        for attempt in range(self.max_retries):
            await self.wait_for_slot(provider)
            try:
                return await operation()
            except RateLimitExceeded as exc:
                last_error = exc
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.base_delay_seconds * 2**attempt)
        raise last_error or RateLimitExceeded(provider)


def _prune(entries: deque[float], now: float) -> None:
    while entries and now - entries[0] >= 1:
        entries.popleft()
