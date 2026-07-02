"""Visible browser driver contract for autonomous browser research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from hydra.browser_automation.policy import host_for_url


@dataclass(frozen=True)
class DriverPage:
    url: str
    title: str = ""
    text: str = ""
    snapshot_bytes: bytes = b""
    automation_blocked: bool = False
    # Landed-page sensitivity signals inspected AFTER redirects resolve, so the
    # runner can re-evaluate the real page (not the declared URL) before capture.
    has_password_field: bool = False
    has_payment_field: bool = False
    has_cookies: bool = False


class BrowserResearchDriver(Protocol):
    requested_urls: list[str]

    async def open_task_group(self, *, task_group_id: str, task_group_label: str) -> None:
        ...

    async def navigate(self, url: str, *, task_group_id: str) -> DriverPage:
        ...

    async def close_task_group(self, task_group_id: str) -> None:
        ...


class FakeBrowserResearchDriver:
    """Offline deterministic driver used by tests."""

    def __init__(self, pages: dict[str, DriverPage], *, cancel_after_navigation: bool = False) -> None:
        self.pages = dict(pages)
        self.cancel_after_navigation = cancel_after_navigation
        self.requested_urls: list[str] = []
        self.tab_groups: dict[str, list[str]] = {}
        self.closed_groups: list[str] = []

    async def open_task_group(self, *, task_group_id: str, task_group_label: str) -> None:
        self.tab_groups.setdefault(task_group_id, [])

    async def navigate(self, url: str, *, task_group_id: str) -> DriverPage:
        self.requested_urls.append(url)
        host = host_for_url(url)
        self.tab_groups.setdefault(task_group_id, [])
        if host not in self.tab_groups[task_group_id]:
            self.tab_groups[task_group_id].append(host)
        return self.pages.get(url) or DriverPage(url=url, title=url, text="", snapshot_bytes=b"")

    async def close_task_group(self, task_group_id: str) -> None:
        self.closed_groups.append(task_group_id)


class PlaywrightBrowserResearchDriver:
    """Headed Playwright driver for public/local pages.

    Playwright is imported lazily so tests and offline installs do not need a
    real browser. The caller must install browser binaries separately.
    """

    def __init__(self, *, headless: bool = False) -> None:
        self.headless = headless
        self.requested_urls: list[str] = []
        self._playwright = None
        self._browser = None
        self._contexts: dict[str, object] = {}

    async def open_task_group(self, *, task_group_id: str, task_group_label: str) -> None:
        self._contexts.setdefault(task_group_id, None)

    async def _ensure_context(self, task_group_id: str):
        if self._playwright is None:
            from playwright.async_api import async_playwright  # type: ignore[import-not-found]

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
        if self._contexts.get(task_group_id) is None:
            self._contexts[task_group_id] = await self._browser.new_context()  # type: ignore[union-attr]
        return self._contexts[task_group_id]

    async def navigate(self, url: str, *, task_group_id: str) -> DriverPage:
        context = await self._ensure_context(task_group_id)
        page = await context.new_page()  # type: ignore[attr-defined]
        self.requested_urls.append(url)
        response = await page.goto(url, wait_until="domcontentloaded")
        if response is not None and response.status in {401, 403, 407, 429}:
            return DriverPage(url=url, title=await page.title(), automation_blocked=True)
        text = await page.locator("body").inner_text(timeout=5000)
        snapshot = (await page.content()).encode()
        has_password = await page.locator("input[type=password]").count() > 0
        payment_selector = (
            "input[autocomplete*='cc-'], input[name*='card'], input[name*='cvc'], "
            "input[name*='cvv'], input[autocomplete='cc-number']"
        )
        has_payment = await page.locator(payment_selector).count() > 0
        # NB: deliberately do NOT report context-wide cookies here. Cookies are
        # normal once a session starts; feeding a context-scoped has_cookies into
        # the landed-page hard-block check would discard every page after the
        # first cookie is set, even on an approved host (03-06 over-block fix).
        return DriverPage(
            url=page.url,
            title=await page.title(),
            text=text,
            snapshot_bytes=snapshot,
            has_password_field=has_password,
            has_payment_field=has_payment,
        )

    async def close_task_group(self, task_group_id: str) -> None:
        context = self._contexts.pop(task_group_id, None)
        if context is not None:
            await context.close()  # type: ignore[attr-defined]

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
