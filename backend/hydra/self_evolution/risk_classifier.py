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

import re

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


_KEY_RE = re.compile(r"^(\s*)([A-Za-z0-9_-]+)\s*:")


def _protected_block_edit(unified_diff: str) -> str | None:
    """Detect an add/remove of a value *under* a protected skill field.

    ``SKILL_PROTECTED_FIELDS`` like ``allowed_capabilities`` are YAML block lists:
    a capability grant adds ``+  - run_shell`` while the ``allowed_capabilities:``
    key line stays as unchanged context. The colon-token scan therefore misses
    it. Here we track the enclosing YAML key by indentation across context AND
    changed lines (the ``+``/``-``/`` `` prefix is stripped so original
    indentation is preserved), and flag any changed line whose nearest enclosing
    key — or the changed key itself — is protected (HL-TRUST-20, list-topology
    evasion). Returns the matched field name, else ``None``.
    """
    stack: list[tuple[int, str]] = []
    for raw in (unified_diff or "").splitlines():
        if raw.startswith(("+++", "---")):
            continue
        if raw.startswith("@@"):
            stack = []
            continue
        marker = raw[:1]
        if marker not in ("+", "-", " "):
            continue
        body = raw[1:]
        if not body.strip():
            continue
        changed = marker in ("+", "-")
        indent = len(body) - len(body.lstrip(" "))
        key_match = _KEY_RE.match(body)
        if key_match:
            key_indent = len(key_match.group(1))
            key_name = key_match.group(2).lower()
            while stack and stack[-1][0] >= key_indent:
                stack.pop()
            stack.append((key_indent, key_name))
            if changed and key_name in SKILL_PROTECTED_FIELDS:
                return key_name
            continue
        if changed:
            for enclosing_indent, enclosing_key in reversed(stack):
                if enclosing_indent < indent:
                    if enclosing_key in SKILL_PROTECTED_FIELDS:
                        return enclosing_key
                    break
    return None


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
    if "skill_capability_field" in FULL_ACCESS_EXCLUDED_ACTIONS:
        for field_name in SKILL_PROTECTED_FIELDS:
            token = f"{field_name}:"
            if any(token in line for line in changed):
                return REVIEW_REQUIRED, f"skill_capability_field ({field_name})"
        # Block-list value edits (e.g. `+  - run_shell` under an unchanged
        # `allowed_capabilities:` header) carry no `field:` token on the changed
        # line, so match them by their enclosing YAML key instead.
        block_field = _protected_block_edit(unified_diff)
        if block_field is not None:
            return REVIEW_REQUIRED, f"skill_capability_field ({block_field})"

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
