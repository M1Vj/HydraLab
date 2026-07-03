from __future__ import annotations

import re
from typing import Any

from hydra.agents.policy import WriteRequest, evaluate_write
from hydra.services.browser.actions import TRUST_LEVEL_UNTRUSTED


def motivating_excerpt(text: str, limit: int = 280) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    return compact[:limit]


async def route_untrusted_browser_proposal(
    repo: Any,
    *,
    project_id: str,
    url: str,
    page_text: str,
    proposed_action: str,
    mode: str,
) -> tuple[str, dict[str, Any]]:
    decision = evaluate_write(
        WriteRequest(
            mode=mode,
            action_kind=f"browser.{proposed_action}",
            target_kind="browser_page",
            target_ref=url,
            trust_origin=TRUST_LEVEL_UNTRUSTED,
            justification_trust=TRUST_LEVEL_UNTRUSTED,
        )
    )
    item = await repo.create_review_item(
        {
            "project_id": project_id,
            "item_type": "browser-untrusted-proposal",
            "title": "Review browser page proposal",
            "summary": decision.reason,
            "origin_type": "browser",
            "origin_id": url,
            "target_type": "browser-action",
            "payload": {
                "proposed_action": proposed_action,
                "origin_url": url,
                "trust_level": TRUST_LEVEL_UNTRUSTED,
                "motivating_excerpt": motivating_excerpt(page_text),
            },
        }
    )
    return decision.reason, item
