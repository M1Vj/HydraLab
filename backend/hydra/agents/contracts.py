"""HydraLab-owned, framework-independent agent runtime vocabulary.

Every public agent concept HydraLab exposes lives here in HydraLab's own terms —
``Run``, ``Tool``, ``Skill``, ``Trace``, ``Artifact``, ``Approval`` — so that no
router, model, or UI ever depends on an external agent-framework type
(HL-ASSIST-01). This module MUST NOT import from any agent framework
(openai / langgraph / pydantic_ai / crewai); it is pure standard-library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# Public runtime vocabulary — the only names a public run result may expose.
PUBLIC_VOCABULARY = ("Run", "Tool", "Skill", "Trace", "Artifact", "Approval")


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    FAILED = "failed"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DENIED = "denied"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLOSED = "closed"


@dataclass
class Skill:
    """A HydraLab-managed capability bundle declared by front matter."""

    id: str
    name: str
    scope: str
    allowed_capabilities: list[str] = field(default_factory=list)
    risk_level: str = "unknown"
    requires_approval: bool = True
    enabled: bool = False

    def permits(self, capability: str) -> bool:
        return capability in self.allowed_capabilities


@dataclass
class Tool:
    """A HydraLab managed capability a skill may invoke during a run."""

    name: str
    capability: str
    description: str = ""


@dataclass
class TraceStep:
    """One incrementally-persisted step in a run trace."""

    index: int
    kind: str
    status: str = StepStatus.COMPLETED.value
    summary: str = ""
    tokens: int = 0
    trust_origin: str = "user"
    skill_id: Optional[str] = None
    capability: Optional[str] = None
    denied_capability: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "status": self.status,
            "summary": self.summary,
            "tokens": self.tokens,
            "trust_origin": self.trust_origin,
            "skill_id": self.skill_id,
            "capability": self.capability,
            "denied_capability": self.denied_capability,
        }


@dataclass
class Trace:
    """The ordered, incrementally-persisted record of a run's steps."""

    run_id: str
    steps: list[TraceStep] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(step.tokens for step in self.steps)

    def public_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "steps": [step.public_dict() for step in self.steps]}


@dataclass
class Artifact:
    """A concrete output a run produced, in HydraLab terms."""

    id: str
    kind: str
    ref: str = ""
    summary: str = ""

    def public_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "ref": self.ref, "summary": self.summary}


@dataclass
class Approval:
    """A per-item accept/reject gate for a substantive write."""

    id: str
    action_kind: str
    status: str = ApprovalStatus.PENDING.value
    decision: Optional[str] = None
    reason: str = ""
    trust_origin: str = "user"
    target_kind: Optional[str] = None
    target_ref: Optional[str] = None
    summary: str = ""

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_kind": self.action_kind,
            "status": self.status,
            "decision": self.decision,
            "reason": self.reason,
            "trust_origin": self.trust_origin,
            "target_kind": self.target_kind,
            "target_ref": self.target_ref,
            "summary": self.summary,
        }


@dataclass
class Run:
    """A HydraLab run — the public unit of agent work."""

    id: str
    project_id: str
    mode: str
    status: str = RunStatus.QUEUED.value
    trace: Trace = field(default_factory=lambda: Trace(run_id=""))
    artifacts: list[Artifact] = field(default_factory=list)
    approvals: list[Approval] = field(default_factory=list)

    def public_result(self) -> dict[str, Any]:
        """Expose the outcome only through HydraLab's own runtime vocabulary."""

        return {
            "vocabulary": list(PUBLIC_VOCABULARY),
            "run": {
                "id": self.id,
                "project_id": self.project_id,
                "mode": self.mode,
                "status": self.status,
            },
            "trace": self.trace.public_dict(),
            "artifacts": [artifact.public_dict() for artifact in self.artifacts],
            "approvals": [approval.public_dict() for approval in self.approvals],
        }
