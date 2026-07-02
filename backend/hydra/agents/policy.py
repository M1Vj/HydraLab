"""Agent Access Mode policy and the every-mode hard-limit chokepoint.

There is exactly ONE Agent Access Mode control with exactly three canonical
values (DEC-5): ``passive``, ``copilot``, ``full_access``. No fourth peer mode
exists. Every substantive write passes through :func:`evaluate_write`, the single
chokepoint that enforces the canonical hard limits (DEC-6, DEC-11, Section 29.5)
and the Full-Access exclusion set (Section 29.6, HL-MODE-05).

This module is pure standard-library and imports no agent framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

PASSIVE = "passive"
COPILOT = "copilot"
FULL_ACCESS = "full_access"

# The complete, ordered set of canonical Agent Access Mode ids (DEC-5).
VALID_MODES = (PASSIVE, COPILOT, FULL_ACCESS)


class AgentAccessMode(str, Enum):
    PASSIVE = PASSIVE
    COPILOT = COPILOT
    FULL_ACCESS = FULL_ACCESS


class InvalidModeError(ValueError):
    """Raised when a stored mode value is outside the canonical set."""


def normalize_mode(value: object) -> str:
    """Return a canonical mode id or raise :class:`InvalidModeError`.

    Any value outside ``passive``/``copilot``/``full_access`` is rejected
    (HL-MODE-01) — there is no fourth peer mode and no closed-loop-autonomy id.
    """

    text = str(value or "").strip().lower()
    if text not in VALID_MODES:
        raise InvalidModeError(
            f"invalid Agent Access Mode {value!r}; must be one of {', '.join(VALID_MODES)}"
        )
    return text


class Outcome(str, Enum):
    APPLY = "apply"
    APPROVAL_REQUIRED = "approval_required"
    REVIEW_INBOX = "review_inbox"
    BLOCKED = "blocked"


TRUST_UNTRUSTED = "untrusted-external"

# High-risk categories that may never auto-apply in any mode (Section 29.5).
HIGH_RISK_CATEGORIES = frozenset(
    {
        "secrets",
        "credentials",
        "provider_key",
        "hidden_browser_data",
        "ignored_path",
        "experiment_execution",
        "purchase",
        "publish",
        "destructive_git",
        "irreversible_delete",
    }
)

# Arbitrary code / shell execution has no surface at all (DEC-6).
CODE_EXECUTION_CATEGORIES = frozenset({"shell", "code_execution", "arbitrary_code"})

# Action kinds Full Access must never auto-apply — they downgrade to an approval
# item even when Full Access is enabled (Section 29.6, HL-MODE-05).
FULL_ACCESS_EXCLUDED_ACTIONS = frozenset(
    {
        "skill_capability_field",  # allowed_capabilities/risk_level/requires_approval/scope/enabled_by_default
        "permission_setting",
        "privacy_setting",
        "consent_setting",
        "provider_routing",
    }
)

# Context files protected from any untrusted-provenance auto-write (DEC-11).
PROTECTED_CONTEXT_FILES = frozenset({"SOUL.md", "USER.md", "MEMORY.md", "HYDRA.md"})


@dataclass
class WriteRequest:
    """A proposed substantive write evaluated against the active mode."""

    mode: str
    action_kind: str
    target_kind: Optional[str] = None
    target_ref: Optional[str] = None
    risk_level: str = "low"
    # Provenance of the write target itself.
    trust_origin: str = "user"
    # Provenance of the justification/content/trigger behind the write.
    justification_trust: str = "user"
    capability: Optional[str] = None
    high_risk_category: Optional[str] = None
    full_access_enabled: bool = False


@dataclass
class PolicyDecision:
    outcome: str
    reason: str
    logged: bool = True
    checkpoint_required: bool = False
    review_inbox: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def applied(self) -> bool:
        return self.outcome == Outcome.APPLY.value


def _is_untrusted(value: str) -> bool:
    return str(value or "").lower() in {TRUST_UNTRUSTED, "untrusted", "untrusted-external"}


def _targets_protected_context_file(request: WriteRequest) -> bool:
    ref = (request.target_ref or "").split("/")[-1]
    return ref in PROTECTED_CONTEXT_FILES


def evaluate_write(request: WriteRequest) -> PolicyDecision:
    """The single chokepoint every substantive write passes through.

    Ordering is load-bearing: arbitrary code execution is refused outright; then
    untrusted-provenance content is routed to the Review Inbox in every mode
    (DEC-11); then high-risk categories and the Full-Access exclusion set force an
    approval; only a plain low-risk write in enabled Full Access auto-applies.
    """

    mode = normalize_mode(request.mode)

    # DEC-6 — no arbitrary code/shell execution surface exists in any mode.
    if (request.high_risk_category in CODE_EXECUTION_CATEGORIES) or (
        request.action_kind in CODE_EXECUTION_CATEGORIES
    ):
        return PolicyDecision(
            outcome=Outcome.BLOCKED.value,
            reason="arbitrary code execution is never permitted in any mode",
            logged=True,
        )

    # DEC-11 — untrusted-provenance text is data, not instructions. It may not by
    # itself trigger a write/tool/auto-promotion in ANY mode (including Full
    # Access); it is routed to the Review Inbox.
    if _is_untrusted(request.trust_origin) or _is_untrusted(request.justification_trust):
        return PolicyDecision(
            outcome=Outcome.REVIEW_INBOX.value,
            reason="untrusted-provenance content is data not instructions; routed to Review Inbox",
            logged=True,
            review_inbox=True,
        )

    # DEC-11 — a protected context file (SOUL/USER/MEMORY/HYDRA) NEVER auto-writes,
    # regardless of provenance or mode. Untrusted provenance already returned above;
    # this forces approval even for a trusted, low-risk write under enabled Full
    # Access, matching the "protected files only land via approval" contract.
    if request.action_kind == "context_file_write" and _targets_protected_context_file(request):
        return PolicyDecision(
            outcome=Outcome.APPROVAL_REQUIRED.value,
            reason="protected context file requires explicit approval in every mode",
            logged=True,
        )

    # HL-MODE-05 — Full Access never auto-edits skill capability/permission/
    # privacy/consent/provider-routing settings; these downgrade to approval.
    if request.action_kind in FULL_ACCESS_EXCLUDED_ACTIONS:
        reason = _excluded_action_reason(request.action_kind)
        if mode == FULL_ACCESS:
            return PolicyDecision(
                outcome=Outcome.REVIEW_INBOX.value,
                reason=reason,
                logged=True,
                review_inbox=True,
            )
        return PolicyDecision(
            outcome=Outcome.APPROVAL_REQUIRED.value,
            reason=reason,
            logged=True,
        )

    # Section 29.5 — high-risk categories never auto-apply.
    if request.high_risk_category in HIGH_RISK_CATEGORIES:
        reason = f"high-risk category '{request.high_risk_category}' requires explicit approval"
        if mode == FULL_ACCESS:
            return PolicyDecision(
                outcome=Outcome.REVIEW_INBOX.value,
                reason=reason,
                logged=True,
                review_inbox=True,
            )
        return PolicyDecision(outcome=Outcome.APPROVAL_REQUIRED.value, reason=reason, logged=True)

    # Passive (Suggest-only) — nothing auto-applies; every write is a suggestion.
    if mode == PASSIVE:
        return PolicyDecision(
            outcome=Outcome.APPROVAL_REQUIRED.value,
            reason="passive mode suggests only; no write auto-applies",
            logged=True,
        )

    # Co-pilot (Approve-to-apply) — each substantive write is a per-item approval.
    if mode == COPILOT:
        return PolicyDecision(
            outcome=Outcome.APPROVAL_REQUIRED.value,
            reason="co-pilot mode requires per-item approval",
            logged=True,
        )

    # Full Access — allowed low-risk writes auto-apply with log + checkpoint, but
    # only when explicitly enabled for this project (default OFF).
    if not request.full_access_enabled:
        return PolicyDecision(
            outcome=Outcome.APPROVAL_REQUIRED.value,
            reason="full access is not enabled for this project; falling back to approval",
            logged=True,
        )
    if str(request.risk_level or "").lower() != "low":
        return PolicyDecision(
            outcome=Outcome.APPROVAL_REQUIRED.value,
            reason="full access auto-applies only low-risk writes; this one requires approval",
            logged=True,
        )
    return PolicyDecision(
        outcome=Outcome.APPLY.value,
        reason="low-risk write auto-applied under full access with log and checkpoint",
        logged=True,
        checkpoint_required=True,
    )


def _excluded_action_reason(action_kind: str) -> str:
    if action_kind == "skill_capability_field":
        return "skill capability field is a hard exclusion"
    if action_kind == "provider_routing":
        return "provider routing is a hard exclusion"
    return f"{action_kind.replace('_', ' ')} is a hard exclusion"
