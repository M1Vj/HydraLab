"""Browser co-pilot service surface."""

from hydra.services.browser.actions import (
    BROWSER_COPILOT_ACTIONS,
    BrowserActionRequest,
    ExcludedBrowserContext,
    browser_copilot_tool_descriptors,
)
from hydra.services.browser.copilot import BrowserCopilotService
from hydra.services.browser.repository import BrowserActionLogRepository, BrowserHostPermissionRepository

__all__ = [
    "BROWSER_COPILOT_ACTIONS",
    "BrowserActionLogRepository",
    "BrowserActionRequest",
    "BrowserCopilotService",
    "BrowserHostPermissionRepository",
    "ExcludedBrowserContext",
    "browser_copilot_tool_descriptors",
]
