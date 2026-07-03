"""Trust-origin gate (branch 03-05, HL-TRUST-21).

Untrusted-provenance content is data, not a change request. A skill/prompt/code
edit proposed because a PDF/browser page/DOCX/Markdown file "said so" is
untrusted-traced: it is stamped ``trust_level=untrusted-external``, routed to the
Review Inbox, and never reaches the apply path. Only a user-originated trigger
(a typed request, an explicit accept) authorizes a self-evolution run.

Trust semantics mirror ``hydra.agents.policy`` (the single write chokepoint) so
provenance is judged identically here and there.
"""

from __future__ import annotations

from hydra.agents.policy import TRUST_UNTRUSTED as _POLICY_TRUST_UNTRUSTED

TRUST_USER = "user"
TRUST_UNTRUSTED = _POLICY_TRUST_UNTRUSTED  # "untrusted-external"

_UNTRUSTED_VALUES = {TRUST_UNTRUSTED, "untrusted", "untrusted-external"}


def is_untrusted(value: object) -> bool:
    """True when ``value`` names any untrusted-provenance trust level."""
    return str(value or "").strip().lower() in _UNTRUSTED_VALUES


def stamp_trust_level(*trust_values: object) -> str:
    """Return the effective trust level for a proposal.

    If ANY contributing provenance (write target or justification) is untrusted,
    the whole proposal is ``untrusted-external`` — untrusted taint is sticky and
    can never be laundered into a trusted, appliable change.
    """
    if any(is_untrusted(value) for value in trust_values):
        return TRUST_UNTRUSTED
    return TRUST_USER
