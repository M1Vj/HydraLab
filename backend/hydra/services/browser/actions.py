from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from hydra.services.assistant.untrusted import assemble_untrusted_region


TRUST_LEVEL_UNTRUSTED = "untrusted-external"


@dataclass(frozen=True)
class BrowserCopilotAction:
    name: str
    label: str
    verb: str
    read_only: bool = False


BROWSER_COPILOT_ACTIONS: tuple[BrowserCopilotAction, ...] = (
    BrowserCopilotAction("search", "Web search", "Search", read_only=True),
    BrowserCopilotAction("save-source", "Save source", "Save source"),
    BrowserCopilotAction("save-snapshot", "Save snapshot", "Save snapshot"),
    BrowserCopilotAction("extract-metadata", "Extract metadata", "Extract metadata"),
    BrowserCopilotAction("create-note", "Create note", "Create note"),
)


ACTION_BY_NAME = {action.name: action for action in BROWSER_COPILOT_ACTIONS}


@dataclass(frozen=True)
class ExcludedBrowserContext:
    incognito: bool = False
    private: bool = False
    has_password_field: bool = False
    has_payment_field: bool = False
    has_cookies: bool = False
    browser_internal: bool = False
    blocked_domain: bool = False
    hidden_session_data: bool = False

    def excluded(self) -> bool:
        return any(
            (
                self.incognito,
                self.private,
                self.has_password_field,
                self.has_payment_field,
                self.has_cookies,
                self.browser_internal,
                self.blocked_domain,
                self.hidden_session_data,
            )
        )


@dataclass(frozen=True)
class BrowserActionRequest:
    project_id: str
    action: str
    url: str
    title: str = ""
    page_text: str = ""
    host: str = ""
    mode: str = "copilot"
    task_group_id: str | None = None
    task_group_label: str = ""
    user_triggered: bool = True
    context: ExcludedBrowserContext | None = None

    def resolved_host(self) -> str:
        if self.host:
            return self.host.lower()
        return (urlparse(self.url).netloc or "").lower()

    def action_descriptor(self) -> BrowserCopilotAction:
        try:
            return ACTION_BY_NAME[self.action]
        except KeyError as exc:
            raise ValueError(f"unknown browser action: {self.action}") from exc

    def untrusted_region(self) -> dict[str, Any]:
        return assemble_untrusted_region(self.page_text, provenance=TRUST_LEVEL_UNTRUSTED)


def browser_copilot_tool_descriptors(host: str) -> list[dict[str, Any]]:
    clean_host = (host or "").lower()
    return [
        {
            "name": f"browser.{action.name}",
            "description": f"{action.label} for the active browser page.",
            "verb": action.verb,
            "host": clean_host,
            "read_only": action.read_only,
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "host": {"type": "string", "const": clean_host},
                    "verb": {"type": "string", "const": action.verb},
                },
                "required": ["url", "host", "verb"],
            },
        }
        for action in BROWSER_COPILOT_ACTIONS
    ]
