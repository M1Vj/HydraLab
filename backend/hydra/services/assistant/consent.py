from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Conservative allowlist (DEC-2 / Section 33): only these leave the machine by default.
ALLOWLIST_TYPES = {"active_file", "selection", "attachment", "explicit_attachment"}

# Per-type opt-in categories (default OFF). Map a ref type -> the opt-in flag it needs.
OPT_IN_FOR_TYPE = {
    "pdf": "all_pdfs_extracted_text",
    "note": "full_notes_corpus",
    "saved_chat": "saved_chats",
    "agent_run": "agent_run_logs",
    "project_metadata": "project_metadata",
    "browser_event": "browser_page_text",
    "browser": "browser_page_text",
}

# Ambient/bulk category names (never sent unless their opt-in is granted).
AMBIENT_CATEGORIES = {
    "full_notes_corpus",
    "all_pdfs_extracted_text",
    "saved_chats",
    "agent_run_logs",
    "project_metadata",
    "browser_page_text",
}

HARD_BLOCK_SUFFIXES = (".env",)
HARD_BLOCK_TOKENS = ("credential", "secret", "password", "id_rsa", ".pem", ".key")
DEFAULT_IGNORED = (".git", ".env", ".hydralab/cache", ".hydralab/temp")


@dataclass
class SendScopeItem:
    ref_type: str
    id_or_path: str
    locator: dict[str, Any] = field(default_factory=dict)
    label: str = ""


@dataclass
class ResolvedScope:
    included: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    blocked: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_hard_block(self) -> bool:
        return bool(self.blocked)


class HardBlockedError(Exception):
    def __init__(self, item: dict[str, Any]) -> None:
        super().__init__(item.get("reason", "hard-blocked category"))
        self.item = item


def _is_hard_blocked(item: SendScopeItem, ignored_paths: list[str]) -> str | None:
    path = (item.id_or_path or "").lower()
    if item.locator.get("incognito") or item.locator.get("private"):
        return "private/incognito browser data cannot be sent to a provider"
    if item.ref_type in {"secret", "credential"}:
        return f"{item.ref_type} is a hard-blocked category"
    if path.endswith(HARD_BLOCK_SUFFIXES):
        return f"{item.id_or_path} is a credential/secret file and is a hard-blocked category"
    if any(token in path for token in HARD_BLOCK_TOKENS):
        return f"{item.id_or_path} matches a hard-blocked credential pattern"
    for ignored in [*DEFAULT_IGNORED, *ignored_paths]:
        ignored = ignored.lower().strip("/")
        if ignored and (path == ignored or path.startswith(ignored + "/")):
            return f"{item.id_or_path} is inside an ignored path ({ignored})"
    return None


def resolve_send_scope(
    items: list[SendScopeItem],
    *,
    g3_enabled: bool,
    offline_only: bool,
    opt_ins: dict[str, bool],
    ignored_paths: list[str] | None = None,
    ambient_categories: list[str] | None = None,
) -> ResolvedScope:
    """Resolve which context refs may leave the machine.

    - Offline-only or G3 off -> nothing leaves (raise-free: everything excluded).
    - Hard-blocked categories -> blocked (caller MUST refuse, not silently drop).
    - Allowlist types -> included.
    - Opt-in / ambient categories -> included only when their opt-in flag is true.
    """
    ignored_paths = ignored_paths or []
    opt_ins = opt_ins or {}
    scope = ResolvedScope()

    for item in items:
        reason = _is_hard_blocked(item, ignored_paths)
        record = {
            "type": item.ref_type,
            "id_or_path": item.id_or_path,
            "locator": item.locator,
            "label": item.label or item.id_or_path,
        }
        if reason:
            scope.blocked.append({**record, "reason": reason})
            continue
        if offline_only:
            scope.excluded.append({**record, "reason": "offline-only mode blocks all provider sends"})
            continue
        if not g3_enabled:
            scope.excluded.append({**record, "reason": "provider send gate G3 is not granted"})
            continue

        opt_in_flag = OPT_IN_FOR_TYPE.get(item.ref_type)
        if opt_in_flag is not None:
            if opt_ins.get(opt_in_flag, False):
                scope.included.append(record)
            else:
                scope.excluded.append({**record, "reason": f"{opt_in_flag} opt-in is off"})
            continue

        if item.ref_type in ALLOWLIST_TYPES:
            scope.included.append(record)
        else:
            scope.excluded.append({**record, "reason": f"{item.ref_type} is not in the conservative allowlist"})

    # Ambient categories present in the project but not explicitly attached.
    for category in ambient_categories or []:
        record = {"type": category, "id_or_path": category, "locator": {}, "label": category}
        if offline_only or not g3_enabled or not opt_ins.get(category, False):
            scope.excluded.append({**record, "reason": f"{category} is opt-in and defaults off"})
        else:
            scope.included.append(record)

    return scope
