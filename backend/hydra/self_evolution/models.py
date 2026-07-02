"""Value objects for a self-evolution proposal (branch 03-05).

The persisted row is ``hydra.database.models.SelfEvolutionChange``; this module
holds the in-memory ``ProposedChange`` a caller hands to the service, keeping the
service signature small and the SQLModel table free of construction logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Category taxonomy for a typed diff (HL-ASSIST-30).
SKILL = "skill"
PROMPT = "prompt"
SETTING = "setting"
APP_CODE = "app_code"
VALID_CATEGORIES = frozenset({SKILL, PROMPT, SETTING, APP_CODE})


@dataclass
class ProposedChange:
    """A single typed diff a caller proposes into a change-set.

    ``unified_diff`` is the human-readable rendering shown before approval;
    ``new_content`` is the exact payload written to ``target_path`` on apply.
    ``test_plan`` names the verification-allowlist commands that gate the change.
    ``origin_trust``/``justification_trust`` carry provenance: if either is
    untrusted-external the proposal is stamped untrusted and barred from apply.
    """

    category: str
    target_path: str
    unified_diff: str
    new_content: str = ""
    test_plan: list[str] = field(default_factory=list)
    origin: str = "user"
    origin_trust: str = "user"
    justification_trust: str = "user"

    def normalized_category(self) -> str:
        text = str(self.category or "").strip().lower()
        return text if text in VALID_CATEGORIES else "app_code"
