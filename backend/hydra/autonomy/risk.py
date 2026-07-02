"""Fixed low/medium/high autonomy risk classifier."""

from __future__ import annotations

from typing import Any

LOW_ACTIONS = {
    "read",
    "retrieve",
    "retrieval",
    "summarize",
    "summarization",
    "rank",
    "local_ranking",
    "draft_artifact",
    "non_destructive_draft",
}
MEDIUM_ACTIONS = {
    "file_write",
    "project_file_write",
    "write_note",
    "prompt_edit",
    "skill_edit",
    "settings_edit",
    "task_state_change",
    "checkpoint_create",
    "metadata_cleanup",
    "context_file_write",
}
HIGH_ACTIONS = {
    "run_code",
    "shell",
    "code_execution",
    "spend_money",
    "external_compute",
    "publish_external",
    "external_export",
    "delete_file",
    "restore_file",
    "claim_support_change",
    "manuscript_conclusion_change",
    "browser_permission_change",
    "provider_credential_change",
    "application_code_edit",
}

class RiskClassifier:
    def classify(self, action: Any) -> str:
        explicit = _get(action, "risk_level")
        if str(explicit).lower() in {"low", "medium", "high"}:
            return str(explicit).lower()
        candidates = {
            str(_get(action, "action_kind") or "").lower(),
            str(_get(action, "action_type") or "").lower(),
            str(_get(action, "category") or "").lower(),
            str(_get(action, "high_risk_category") or "").lower(),
        }
        text = " ".join(
            str(_get(action, field) or "").lower()
            for field in ("summary", "target_kind", "target_ref", "capability")
        )
        if candidates & HIGH_ACTIONS:
            return "high"
        if candidates & MEDIUM_ACTIONS:
            return "medium"
        if candidates & LOW_ACTIONS:
            return "low"
        if any(token in text for token in ("delete", "restore", "credential", "provider", "publish", "external", "run code")):
            return "high"
        if any(token in text for token in ("write", "edit", "setting", "task state", "checkpoint")):
            return "medium"
        if any(token in text for token in ("summarize", "summary", "retrieve", "rank", "read-only", "read only")):
            return "low"
        return "high"

def _get(action: Any, name: str) -> Any:
    if isinstance(action, dict):
        return action.get(name)
    return getattr(action, name, None)
