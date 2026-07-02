"""Self-evolution risk classifier (branch 03-05, HL-TRUST-20).

Maps each diff to ``auto_eligible`` or ``review_required``. A diff is
``review_required`` — force-routed to the Review Inbox and NEVER auto-applied,
even under Full Access — when it edits:

- a skill ``allowed_capabilities`` / ``risk_level`` / ``requires_approval`` /
  ``scope`` / ``enabled_by_default`` field (``skill_capability_field``),
- a permission / privacy / consent (G1/G2/G3) setting,
- provider routing / ``[providers]`` config (``provider_routing``), or
- a protected context file (``SOUL.md`` / ``USER.md`` / ``MEMORY.md`` /
  ``HYDRA.md``).

The protected-target vocabulary is imported from ``hydra.agents.policy`` — the
same ``FULL_ACCESS_EXCLUDED_ACTIONS`` and ``PROTECTED_CONTEXT_FILES`` the write
chokepoint enforces — so this classifier can never drift from the policy.
"""

from __future__ import annotations

from hydra.agents.policy import FULL_ACCESS_EXCLUDED_ACTIONS, PROTECTED_CONTEXT_FILES

AUTO_ELIGIBLE = "auto_eligible"
REVIEW_REQUIRED = "review_required"

# The exact skill descriptor fields that constitute a skill_capability_field edit
# (Section 29.6). Editing any of these can never auto-apply.
SKILL_PROTECTED_FIELDS: tuple[str, ...] = (
    "allowed_capabilities",
    "risk_level",
    "requires_approval",
    "scope",
    "enabled_by_default",
)

# Setting keys that map onto a Full-Access hard exclusion. Grouped by the
# excluded action kind they correspond to (all members of
# FULL_ACCESS_EXCLUDED_ACTIONS), so the mapping is anchored to the policy set.
_SETTING_MARKERS: dict[str, tuple[str, ...]] = {
    "permission_setting": ("permission", "permissions", "allowed_capabilities", "capability"),
    "privacy_setting": ("privacy", "offline_only", "provider_send", "egress"),
    "consent_setting": ("consent", "g1", "g2", "g3", "opt_in", "opt_ins"),
    "provider_routing": ("[providers]", "provider_routing", "routing", "providers.accounts", "api_key_ref"),
}


def _changed_lines(unified_diff: str) -> list[str]:
    """Return added/removed diff lines (excluding hunk/file headers)."""
    lines: list[str] = []
    for raw in (unified_diff or "").splitlines():
        if raw.startswith(("+++", "---", "@@")):
            continue
        if raw.startswith(("+", "-")):
            lines.append(raw[1:].strip().lower())
    return lines


def _basename(path: str) -> str:
    return str(path or "").replace("\\", "/").rsplit("/", 1)[-1]


def classify_diff(category: str, target_path: str, unified_diff: str) -> tuple[str, str]:
    """Classify one diff.

    Returns ``(risk_class, reason)``. ``reason`` names the matched excluded action
    kind or protected target so the routing decision is auditable, never silent.

    ``category`` is accepted for interface parity with the change-set model and
    for future category-specific scans, but no protected-target check below may
    be gated on it — it is proposer-supplied and therefore untrusted as a safety
    signal (see HL-TRUST-20 merge-blocker fix: a mislabeled category must never
    bypass a protected-field scan).
    """
    del category  # intentionally unused — see docstring
    changed = _changed_lines(unified_diff)

    # A protected context file is review-only regardless of category.
    if _basename(target_path) in PROTECTED_CONTEXT_FILES:
        return REVIEW_REQUIRED, f"protected context file {_basename(target_path)}"

    # Skill descriptor capability/permission fields (skill_capability_field).
    # Checked regardless of category: a capability escalation is equally
    # dangerous whether it arrives labeled "skill", "app_code", or "prompt" —
    # category is proposer-supplied and MUST NOT gate this scan (mirrors the
    # protected-context-file check above).
    for field_name in SKILL_PROTECTED_FIELDS:
        token = f"{field_name}:"
        if any(token in line for line in changed):
            if "skill_capability_field" in FULL_ACCESS_EXCLUDED_ACTIONS:
                return REVIEW_REQUIRED, f"skill_capability_field ({field_name})"

    # Permission / privacy / consent / provider-routing settings. Also checked
    # regardless of category for the same reason — a "setting"-only gate lets
    # an app_code/prompt diff smuggle a consent or privacy downgrade past
    # review.
    for action_kind, markers in _SETTING_MARKERS.items():
        if action_kind not in FULL_ACCESS_EXCLUDED_ACTIONS:
            continue
        if any(marker in line for line in changed for marker in markers):
            return REVIEW_REQUIRED, action_kind

    # Provider routing can also surface as an app_code / prompt edit; catch the
    # unambiguous marker anywhere so it can never slip past as auto_eligible.
    if "provider_routing" in FULL_ACCESS_EXCLUDED_ACTIONS:
        if any("[providers]" in line or "provider_routing" in line for line in changed):
            return REVIEW_REQUIRED, "provider_routing"

    return AUTO_ELIGIBLE, "no protected target matched"
