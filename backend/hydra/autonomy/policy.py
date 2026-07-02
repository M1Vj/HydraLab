"""Run-governance policy for Phase-3 Autopilot.

Autopilot is a capability layered on the three canonical Agent Access Modes. It
is never a fourth mode and never expands the active mode's authority.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from hydra.agents.policy import normalize_mode
from hydra.agents.runs import DEFAULT_RUN_BUDGET_TOKENS, DEFAULT_WALL_CLOCK_SECONDS
from hydra.database.models import AgentModePolicy

REQUIRED_UNRESOLVED_FIELDS = ("mode", "budget limits", "max loop count", "stop conditions")

class AutonomyPolicyError(ValueError):
    """Raised when an Autopilot run lacks a resolved governance policy."""

@dataclass(frozen=True)
class BudgetLimits:
    tokens: int = DEFAULT_RUN_BUDGET_TOKENS
    wall_clock_seconds: int = DEFAULT_WALL_CLOCK_SECONDS

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "BudgetLimits | None":
        if not isinstance(value, dict):
            return None
        tokens = value.get("tokens", value.get("run_budget_tokens"))
        wall = value.get("wall_clock_seconds")
        if tokens is None or wall is None:
            return None
        return cls(tokens=int(tokens), wall_clock_seconds=int(wall))

    def public_dict(self) -> dict[str, int]:
        return {"tokens": self.tokens, "wall_clock_seconds": self.wall_clock_seconds}

@dataclass(frozen=True)
class AutonomyPolicy:
    mode: str
    allowed_action_types: list[str] = field(default_factory=list)
    blocked_action_types: list[str] = field(default_factory=list)
    budget_limits: BudgetLimits = field(default_factory=BudgetLimits)
    max_loop_count: int = 1
    stop_conditions: list[str] = field(default_factory=lambda: ["max_loop_count"])
    checkpoint_required: bool = True
    approval_required: bool = True
    rollback_behavior: str = "restore_last_checkpoint"
    autopilot_enabled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", normalize_mode(self.mode))
        if self.max_loop_count < 1:
            raise AutonomyPolicyError("max loop count must be >= 1")
        if not self.stop_conditions:
            raise AutonomyPolicyError("stop conditions must include at least one condition")

    def public_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "allowed_action_types": list(self.allowed_action_types),
            "blocked_action_types": list(self.blocked_action_types),
            "budget_limits": self.budget_limits.public_dict(),
            "max_loop_count": self.max_loop_count,
            "stop_conditions": list(self.stop_conditions),
            "checkpoint_required": self.checkpoint_required,
            "approval_required": self.approval_required,
            "rollback_behavior": self.rollback_behavior,
            "autopilot_enabled": self.autopilot_enabled,
        }

    @classmethod
    def from_mapping(cls, data: dict[str, Any], *, autopilot_enabled: bool) -> "AutonomyPolicy":
        budget = BudgetLimits.from_mapping(data.get("budget_limits"))
        missing = []
        if not data.get("mode"):
            missing.append("mode")
        if budget is None:
            missing.append("budget limits")
        if data.get("max_loop_count") is None:
            missing.append("max loop count")
        if not data.get("stop_conditions"):
            missing.append("stop conditions")
        if missing:
            raise _missing_policy_error(missing)
        return cls(
            mode=str(data["mode"]),
            allowed_action_types=list(data.get("allowed_action_types") or []),
            blocked_action_types=list(data.get("blocked_action_types") or []),
            budget_limits=budget,
            max_loop_count=int(data["max_loop_count"]),
            stop_conditions=[str(item) for item in data.get("stop_conditions") or []],
            checkpoint_required=bool(data.get("checkpoint_required", True)),
            approval_required=bool(data.get("approval_required", True)),
            rollback_behavior=str(data.get("rollback_behavior") or "restore_last_checkpoint"),
            autopilot_enabled=autopilot_enabled,
        )

def default_autonomy_policy(mode: str = "passive", *, autopilot_enabled: bool = False) -> AutonomyPolicy:
    return AutonomyPolicy(
        mode=mode,
        allowed_action_types=["read", "summarize", "rank", "draft_artifact"],
        blocked_action_types=[],
        budget_limits=BudgetLimits(),
        max_loop_count=1,
        stop_conditions=["max_loop_count"],
        checkpoint_required=True,
        approval_required=True,
        rollback_behavior="restore_last_checkpoint",
        autopilot_enabled=autopilot_enabled,
    )

def resolve_autonomy_policy(policy: AgentModePolicy | None, *, require_enabled: bool = True) -> AutonomyPolicy:
    """Resolve a per-project policy or raise with all unresolved field names."""

    if policy is None:
        raise _missing_policy_error(REQUIRED_UNRESOLVED_FIELDS)
    if require_enabled and not policy.autopilot_enabled:
        raise AutonomyPolicyError("Autopilot is disabled for this project")
    raw = policy.autonomy_policy_json or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AutonomyPolicyError("missing run-governance policy: autonomy_policy_json is invalid JSON") from exc
    if not data:
        raise _missing_policy_error(REQUIRED_UNRESOLVED_FIELDS)
    if "mode" not in data and policy.default_mode:
        data["mode"] = policy.default_mode
    return AutonomyPolicy.from_mapping(data, autopilot_enabled=bool(policy.autopilot_enabled))

def policy_to_json(policy: AutonomyPolicy) -> str:
    data = policy.public_dict()
    data.pop("autopilot_enabled", None)
    return json.dumps(data, sort_keys=True)

def _missing_policy_error(fields: tuple[str, ...] | list[str]) -> AutonomyPolicyError:
    return AutonomyPolicyError(
        "missing run-governance policy; unresolved fields: " + ", ".join(fields)
    )
