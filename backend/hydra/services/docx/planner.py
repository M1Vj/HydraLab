"""Assistant-proposal → typed DOCX edit plan (HL-WRITE-31, HL-TRUST-30, HL-MODE-30).

Turns assistant proposals into a plan of *typed, inspectable* structural
operations against reader locators, each with a human before/after summary and a
risk label. Trust rules are enforced here, not downstream:

- Every operation whose justification traces to document content is tagged
  ``untrusted-external`` and routed to the Review Inbox with the motivating
  excerpt (DEC-11 / HL-TRUST-30). Document text can never *add*, *remove* or
  *widen* the plan on its own — it only ever produces a pending, human-gated
  proposal.
- The planner NEVER sets ``review_status='approved'``. Nothing is auto-approved,
  so nothing can be auto-applied in any Agent Access Mode. Under Full Access, an
  untrusted-traced edit is additionally downgraded to an approval-required
  Review Inbox item and the downgrade is logged (DEC-5 / HL-MODE-30).
- Operations that would target a protected context file (SOUL/USER/MEMORY/HYDRA)
  are refused outright (Sec 34.4).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .reader import StructuralModel, TRUST_UNTRUSTED_EXTERNAL

OP_TYPES = {
    "replace_text",
    "insert_paragraph",
    "apply_style",
    "update_table",
    "update_citation",
    "comment",
    "delete",
    "other",
}

# Files that DOCX content may never drive edits to (Sec 34.4 / DEC-11).
PROTECTED_CONTEXT_FILES = {"SOUL.md", "USER.md", "MEMORY.md", "HYDRA.md"}

TRUST_TRUSTED = "trusted"

_RISK_BY_OP = {
    "delete": "high",
    "apply_style": "medium",
    "update_table": "medium",
    "update_citation": "medium",
    "other": "medium",
    "replace_text": "low",
    "insert_paragraph": "low",
    "comment": "low",
}


class DocxPlanError(ValueError):
    """Raised when a proposal cannot be turned into a valid typed operation."""


@dataclass
class EditProposal:
    op_type: str
    target_locator: str = ""
    payload: dict = field(default_factory=dict)
    justification: str = ""
    # "assistant" = model reasoning; "document" = derived from DOCX content
    justification_source: str = "assistant"
    motivating_excerpt: str = ""


@dataclass
class PlannedOperation:
    op_type: str
    target_locator: str
    location_label: str
    before_summary: str
    after_summary: str
    payload: dict
    risk_label: str
    trust_level: str
    justification: str
    motivating_excerpt: str
    review_status: str = "pending"
    validation_status: str = "unvalidated"


@dataclass
class EditPlan:
    manuscript: str
    target_relpath: str
    mode: str
    trust_level: str
    operations: list[PlannedOperation] = field(default_factory=list)
    review_inbox_items: list[dict] = field(default_factory=list)
    downgrade_log: list[dict] = field(default_factory=list)


def _snippet(text: str, limit: int = 200) -> str:
    collapsed = " ".join((text or "").split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def _references_protected_file(proposal: EditProposal) -> bool:
    haystacks = [str(proposal.target_locator)]
    for value in proposal.payload.values():
        haystacks.append(str(value))
    blob = " ".join(haystacks)
    return any(name in blob for name in PROTECTED_CONTEXT_FILES)


def _after_summary(op_type: str, payload: dict) -> str:
    if op_type in {"replace_text", "insert_paragraph", "update_table", "update_citation"}:
        return _snippet(str(payload.get("text", "")))
    if op_type == "apply_style":
        return f"apply style → {payload.get('style', '')}"
    if op_type == "comment":
        return f"comment → {_snippet(str(payload.get('text', '')))}"
    if op_type == "delete":
        return "(deleted)"
    return _snippet(str(payload.get("text", payload)))


def build_plan(
    model: StructuralModel,
    proposals: list[EditProposal],
    *,
    manuscript: str,
    target_relpath: str,
    mode: str = "passive",
    project_id: Optional[str] = None,
) -> EditPlan:
    """Convert proposals into a typed, human-gated :class:`EditPlan`.

    ``model`` supplies before-summaries and location labels from the actual
    document (not raw XML), so a reviewer reads what will change. Trust and
    Review-Inbox routing are decided per operation.
    """
    plan = EditPlan(manuscript=manuscript, target_relpath=target_relpath, mode=mode, trust_level=TRUST_TRUSTED)

    for proposal in proposals:
        if proposal.op_type not in OP_TYPES:
            raise DocxPlanError(f"unsupported op_type: {proposal.op_type!r}")
        if _references_protected_file(proposal):
            # A protected context file can never be edited from DOCX content.
            plan.downgrade_log.append(
                {
                    "reason": "protected-context-file-refused",
                    "target_locator": proposal.target_locator,
                    "op_type": proposal.op_type,
                }
            )
            continue

        node = model.find(proposal.target_locator)
        before_summary = _snippet(node.text) if node else ""
        location_label = node.location_label if node else proposal.target_locator

        # Trust is derived from BOTH the caller-declared justification source AND
        # the reader's own trust tag on the targeted node. A client cannot launder
        # a document-derived edit as "assistant"-sourced: any op targeting an
        # untrusted-external document node is always treated as document-traced
        # (routed to the Review Inbox, full-access-downgrade logged).
        node_untrusted = node is not None and getattr(node, "trust_level", None) == TRUST_UNTRUSTED_EXTERNAL
        traces_to_document = proposal.justification_source == "document" or node_untrusted
        trust_level = TRUST_UNTRUSTED_EXTERNAL if traces_to_document else TRUST_TRUSTED

        operation = PlannedOperation(
            op_type=proposal.op_type,
            target_locator=proposal.target_locator,
            location_label=location_label,
            before_summary=before_summary,
            after_summary=_after_summary(proposal.op_type, proposal.payload),
            payload=dict(proposal.payload),
            risk_label=_RISK_BY_OP.get(proposal.op_type, "medium"),
            trust_level=trust_level,
            justification=proposal.justification,
            motivating_excerpt=proposal.motivating_excerpt,
            review_status="pending",
            validation_status="unvalidated",
        )
        plan.operations.append(operation)

        if traces_to_document:
            plan.trust_level = TRUST_UNTRUSTED_EXTERNAL
            plan.review_inbox_items.append(
                {
                    "project_id": project_id,
                    "item_type": "docx-edit-proposal",
                    "title": f"DOCX edit proposal: {proposal.op_type} @ {location_label}",
                    "summary": (
                        "A proposed DOCX edit traces to untrusted document content and "
                        "requires explicit review before it can be applied."
                    ),
                    "origin_type": "docx_document",
                    "target_type": "docx_manuscript",
                    "target_id": target_relpath,
                    "payload": {
                        "op_type": proposal.op_type,
                        "target_locator": proposal.target_locator,
                        "location_label": location_label,
                        "before_summary": before_summary,
                        "after_summary": operation.after_summary,
                        "trust_level": TRUST_UNTRUSTED_EXTERNAL,
                        "motivating_excerpt": proposal.motivating_excerpt,
                    },
                }
            )
            if mode == "full_access":
                # DEC-5 / HL-MODE-30: Full Access must NOT silently auto-apply an
                # untrusted-traced edit — downgrade to approval-required + log.
                plan.downgrade_log.append(
                    {
                        "reason": "full-access-untrusted-downgraded-to-approval",
                        "target_locator": proposal.target_locator,
                        "op_type": proposal.op_type,
                        "trust_level": TRUST_UNTRUSTED_EXTERNAL,
                    }
                )

    return plan
