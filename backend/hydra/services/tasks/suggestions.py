"""Research-linked task suggestion + review-gating pipeline (HL-UX-04..07).

DEC-11: untrusted-provenance justifications are data, not instructions. They can
never auto-activate a task; they route to the Review Inbox for explicit approval.
Suggested and auto-draft tasks are created in the ``draft`` lifecycle state and
only become ``active`` after the researcher accepts them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Justification categories that MUST route through the Review Inbox and never
# auto-activate a task, regardless of Agent Access Mode (HL-UX-06 / DEC-11).
REVIEW_CATEGORIES: frozenset[str] = frozenset(
    {
        "deadline",
        "external_commitment",
        "manuscript_commitment",
        "publication",
        "provider_api",
        "research_direction",
    }
)

# Low-risk categories eligible for settings-gated auto-draft creation (HL-UX-05).
AUTO_DRAFT_CATEGORIES: frozenset[str] = frozenset(
    {
        "follow_up_reading",
        "citation_check",
        "missing_metadata",
        "broken_link",
        "duplicate_source",
        "unread_source",
    }
)


def requires_review(category: Optional[str], trust_origin: str) -> bool:
    """Deadline/commitment/provider/research-direction OR untrusted → review."""
    if trust_origin == "untrusted":
        return True
    return category in REVIEW_CATEGORIES


@dataclass
class TaskProposal:
    title: str
    project_id: Optional[str] = None
    origin: str = "assistant"  # "assistant" (suggestion) | "auto" (draft)
    category: Optional[str] = None
    trust_origin: str = "user"  # "user" | "untrusted"
    summary: str = ""
    detail: str = ""
    origin_type: Optional[str] = None  # e.g. "browser", "chat", "source"
    origin_id: Optional[str] = None
    link: Optional[dict[str, str]] = None  # {target_type, target_id_or_path, link_role?}
    tags: list[str] = field(default_factory=list)


async def propose_task(
    repo: Any,
    proposal: TaskProposal,
    *,
    auto_draft_enabled: bool,
) -> dict[str, Any]:
    """Create a draft/suggested task and/or a Review Inbox item.

    Returns ``{"task": <task|None>, "review_item": <item|None>, "created": bool}``.
    """
    review_needed = requires_review(proposal.category, proposal.trust_origin)

    # HL-UX-05: auto drafts require the opt-in setting. When OFF, no auto task is
    # created; the candidate surfaces only as a Review Inbox item.
    if proposal.origin == "auto" and not auto_draft_enabled:
        review_item = await repo.create_review_item(
            {
                "project_id": proposal.project_id,
                "item_type": f"{proposal.category or 'draft'}-candidate",
                "title": proposal.title,
                "summary": proposal.summary or "Auto-draft tasks are disabled; review required.",
                "origin_type": proposal.origin_type,
                "origin_id": proposal.origin_id,
                "target_type": proposal.link.get("target_type") if proposal.link else None,
                "target_id": proposal.link.get("target_id_or_path") if proposal.link else None,
                "payload": {"auto_draft_enabled": False, "category": proposal.category},
            }
        )
        return {"task": None, "review_item": review_item, "created": False}

    task = await repo.add_task(
        title=proposal.title,
        column="to_do",
        detail=proposal.detail,
        project_id=proposal.project_id,
        tags=proposal.tags,
        origin=proposal.origin,
        assistant_created=True,
        lifecycle_state="draft",
        review_category=proposal.category if review_needed else None,
        trust_origin=proposal.trust_origin,
    )

    if proposal.link:
        await repo.create_task_link(
            task_id=task["id"],
            target_type=proposal.link["target_type"],
            target_id_or_path=proposal.link["target_id_or_path"],
            link_role=proposal.link.get("link_role", "about"),
        )

    review_item = await repo.create_review_item(
        {
            "project_id": proposal.project_id,
            "item_type": "draft_task",
            "title": proposal.title,
            "summary": proposal.summary,
            "origin_type": proposal.origin_type,
            "origin_id": proposal.origin_id,
            "target_type": "task",
            "target_id": task["id"],
            "payload": {
                "origin": proposal.origin,
                "category": proposal.category,
                "requires_review": review_needed,
                "trust_origin": proposal.trust_origin,
                "untrusted": proposal.trust_origin == "untrusted",
                "link": proposal.link,
            },
        }
    )
    return {"task": task, "review_item": review_item, "created": True}
