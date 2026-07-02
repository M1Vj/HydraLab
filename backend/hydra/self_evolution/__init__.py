"""Self-evolving skills & fixer (branch 03-05, Phase-3).

Turns "self-improvement" into an auditable, reversible, never-silent workflow:
``propose → explicit per-change approval → checkpoint → apply → auto-verify →
keep-or-auto-rollback``. Reuses the 03-01 autonomy shell (checkpoint service,
append-only audit ledger) and the fixed verification allowlist runner; it never
forks a second checkpoint/audit system nor widens the allowlist.
"""

from __future__ import annotations

from hydra.self_evolution.models import ProposedChange
from hydra.self_evolution.redactor import redact
from hydra.self_evolution.risk_classifier import (
    AUTO_ELIGIBLE,
    REVIEW_REQUIRED,
    classify_diff,
)
from hydra.self_evolution.service import SelfEvolutionError, SelfEvolutionService
from hydra.self_evolution.trust_gate import (
    TRUST_UNTRUSTED,
    TRUST_USER,
    is_untrusted,
    stamp_trust_level,
)
from hydra.self_evolution.verification import (
    TestPlanError,
    VerificationOutcome,
    validate_test_plan,
)

__all__ = [
    "AUTO_ELIGIBLE",
    "REVIEW_REQUIRED",
    "ProposedChange",
    "SelfEvolutionError",
    "SelfEvolutionService",
    "TRUST_UNTRUSTED",
    "TRUST_USER",
    "TestPlanError",
    "VerificationOutcome",
    "classify_diff",
    "is_untrusted",
    "redact",
    "stamp_trust_level",
    "validate_test_plan",
]
