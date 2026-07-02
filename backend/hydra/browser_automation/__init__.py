"""Approved autonomous browser research surface."""

from hydra.browser_automation.capture import BrowserCaptureService, SourcePromotionRequest
from hydra.browser_automation.driver import DriverPage, FakeBrowserResearchDriver
from hydra.browser_automation.policy import (
    BrowserAutomationContext,
    BrowserAutomationPolicy,
    BrowserNavigationDecision,
    ProviderRateLimiter,
)
from hydra.browser_automation.runner import (
    AutonomousBrowserResearchRunner,
    BrowserResearchRunResult,
    BrowserResearchStep,
    BrowserRunRequest,
)

__all__ = [
    "AutonomousBrowserResearchRunner",
    "BrowserAutomationContext",
    "BrowserAutomationPolicy",
    "BrowserCaptureService",
    "BrowserNavigationDecision",
    "BrowserResearchRunResult",
    "BrowserResearchStep",
    "BrowserRunRequest",
    "DriverPage",
    "FakeBrowserResearchDriver",
    "ProviderRateLimiter",
    "SourcePromotionRequest",
]
