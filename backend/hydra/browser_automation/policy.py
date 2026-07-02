"""Policy checks for autonomous browser research runs."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.browser_bridge import INTERNAL_SCHEMES, TRUST_LEVEL_UNTRUSTED
from hydra.services.browser.repository import BrowserHostPermissionRepository

HOST_PROMPT_CHOICES = ["Allow for this task", "Always allow this host", "Decline/block this host"]
OFFICIAL_API_PROVIDERS = ("Crossref", "OpenAlex", "Semantic Scholar", "arXiv", "Unpaywall", "CORE")


@dataclass(frozen=True)
class BrowserAutomationContext:
    project_id: str
    url: str
    task_group_id: str | None = None
    incognito: bool = False
    private: bool = False
    has_password_field: bool = False
    has_payment_field: bool = False
    has_cookies: bool = False
    browser_internal: bool = False
    hidden_session_data: bool = False
    blocked_domain: bool = False
    automation_blocked: bool = False
    browser_page_text_to_provider: bool = False

    @property
    def host(self) -> str:
        return host_for_url(self.url)


@dataclass(frozen=True)
class BrowserNavigationDecision:
    status: str
    host: str
    reason: str
    prompt_choices: list[str] = field(default_factory=list)
    provider_eligible: bool = False
    fallback_provider: str | None = None
    bypass_attempted: bool = False
    attempted_actions: list[str] = field(default_factory=list)
    trust_level: str = TRUST_LEVEL_UNTRUSTED

    @property
    def allowed(self) -> bool:
        return self.status == "allowed"


@dataclass(frozen=True)
class ProviderRateLimitDecision:
    state: str
    retry_after_seconds: float = 0.0
    reason: str = ""


class ProviderRateLimiter:
    """Aggregate provider rate limiter: 3 req/s plus bounded 429 backoff."""

    def __init__(self, *, max_requests_per_second: int = 3, max_429_retries: int = 2) -> None:
        self.max_requests_per_second = max_requests_per_second
        self.max_429_retries = max_429_retries
        self._request_times: list[float] = []
        self._consecutive_429 = 0

    def before_request(self, now: float | None = None) -> ProviderRateLimitDecision:
        timestamp = now if now is not None else time.monotonic()
        self._request_times = [seen for seen in self._request_times if timestamp - seen < 1.0]
        if len(self._request_times) >= self.max_requests_per_second:
            return ProviderRateLimitDecision(
                state="rate-ceiling",
                retry_after_seconds=max(0.0, 1.0 - (timestamp - self._request_times[0])),
                reason="provider aggregate 3 req/s ceiling reached",
            )
        self._request_times.append(timestamp)
        return ProviderRateLimitDecision(state="allowed")

    def record_response(self, status_code: int) -> ProviderRateLimitDecision:
        if status_code != 429:
            self._consecutive_429 = 0
            return ProviderRateLimitDecision(state="allowed")
        self._consecutive_429 += 1
        if self._consecutive_429 >= self.max_429_retries:
            return ProviderRateLimitDecision(
                state="provider rate-limited",
                reason="provider rate-limited",
            )
        return ProviderRateLimitDecision(
            state="backoff",
            retry_after_seconds=2 ** self._consecutive_429,
            reason="provider returned 429; backing off",
        )


class BrowserAutomationPolicy:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.permissions = BrowserHostPermissionRepository(session)

    async def evaluate_navigation(self, context: BrowserAutomationContext) -> BrowserNavigationDecision:
        host = context.host
        if self._hard_blocked(context):
            return BrowserNavigationDecision(
                status="hard-blocked",
                host=host,
                reason="hard-blocked browser context is excluded from capture and provider context",
                provider_eligible=False,
            )
        if context.automation_blocked:
            return BrowserNavigationDecision(
                status="site-blocks-automation",
                host=host,
                reason="site blocks automation; use official source",
                fallback_provider=self._fallback_provider(context.url),
                bypass_attempted=False,
                attempted_actions=["headed-navigation", "official-api-fallback"],
            )
        permission = await self.permissions.get(context.project_id, host)
        if permission["state"] == "blocked":
            return BrowserNavigationDecision(
                status="blocked",
                host=host,
                reason=f"host {host} is blocked",
                provider_eligible=False,
            )
        if permission["state"] in {"allow_for_task", "always_allow_host"}:
            return BrowserNavigationDecision(
                status="allowed",
                host=host,
                reason=f"host {host} allowed",
                provider_eligible=bool(context.browser_page_text_to_provider),
            )
        return BrowserNavigationDecision(
            status="needs-approval",
            host=host,
            reason=f"host {host} requires first-use approval",
            prompt_choices=list(HOST_PROMPT_CHOICES),
            provider_eligible=False,
        )

    def _hard_blocked(self, context: BrowserAutomationContext) -> bool:
        parsed = urlparse(context.url)
        return any(
            (
                parsed.scheme in INTERNAL_SCHEMES,
                context.incognito,
                context.private,
                context.has_password_field,
                context.has_payment_field,
                context.has_cookies,
                context.browser_internal,
                context.hidden_session_data,
                context.blocked_domain,
            )
        )

    def _fallback_provider(self, url: str) -> str:
        doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", url, re.I)
        if doi_match:
            return "Crossref"
        return OFFICIAL_API_PROVIDERS[1]


def host_for_url(url: str) -> str:
    parsed = urlparse(str(url))
    return (parsed.netloc or parsed.path).lower()
