"""Managed-capability permission check (HL-ASSIST-06).

Every managed capability call is checked against the active skill's declared
``allowed_capabilities`` and denied calls are recorded in the run trace with the
skill id and the denied capability. HydraLab exposes no public plugin API or MCP
in this branch — capabilities are HydraLab-owned only.
"""

from __future__ import annotations

from dataclasses import dataclass

from hydra.agents.contracts import Skill


class CapabilityDenied(PermissionError):
    """Raised when a skill invokes a capability outside its allowances."""

    def __init__(self, skill_id: str, capability: str):
        self.skill_id = skill_id
        self.capability = capability
        super().__init__(
            f"skill '{skill_id}' is not permitted to use capability '{capability}'"
        )


@dataclass
class CapabilityCheck:
    allowed: bool
    skill_id: str
    capability: str
    reason: str = ""


def check_capability(skill: Skill, capability: str) -> CapabilityCheck:
    """Return whether ``skill`` may use ``capability`` (never raises)."""

    if skill.permits(capability):
        return CapabilityCheck(allowed=True, skill_id=skill.id, capability=capability)
    return CapabilityCheck(
        allowed=False,
        skill_id=skill.id,
        capability=capability,
        reason=f"capability '{capability}' is outside the skill's allowed capabilities",
    )


def require_capability(skill: Skill, capability: str) -> None:
    """Enforce a capability allowance, raising :class:`CapabilityDenied`."""

    if not skill.permits(capability):
        raise CapabilityDenied(skill.id, capability)
