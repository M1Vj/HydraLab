"""Conflict-safe Markdown collaboration session service."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.agents.policy import TRUST_UNTRUSTED
from hydra.autonomy.gate import ActionGate, GateResult, GovernedAction
from hydra.collaboration.identity import IdentityProvider
from hydra.collaboration.transport import InProcessSyncTransport

SYNC_STATES = ("offline", "connecting", "synced", "syncing", "conflict", "revoked")


@dataclass(frozen=True)
class CollaborativeEdit:
    collaborator_id: str
    text: str
    summary: str
    insert_at: int | None = None
    replace_range: tuple[int, int] | None = None


@dataclass(frozen=True)
class ConflictCopy:
    path: str
    content: str


@dataclass(frozen=True)
class ConflictSummary:
    document_id: str
    summary: str
    actions: tuple[str, ...] = ("choose-winner", "merge-manually")


@dataclass
class ReconciliationResult:
    sync_state: str
    conflict_copy: ConflictCopy | None = None
    conflict_summary: ConflictSummary | None = None


@dataclass
class CollaborationSession:
    document_id: str
    base_content: str
    content: str
    sync_state: str = "offline"
    pending_edits: list[CollaborativeEdit] = field(default_factory=list)

    @classmethod
    def open_document(cls, document_id: str, content: str) -> "CollaborationSession":
        return cls(document_id=document_id, base_content=content, content=content, sync_state="synced")

    @classmethod
    async def start_if_enabled(
        cls,
        session: AsyncSession,
        *,
        project_id: str,
        document_id: str,
        initial_content: str,
        transport: InProcessSyncTransport,
    ) -> "CollaborationSession":
        settings = await IdentityProvider(session).settings(project_id)
        instance = cls.open_document(document_id, initial_content)
        if not settings.enabled:
            instance.sync_state = "offline"
            return instance
        instance.sync_state = "connecting"
        transport.connection_attempts += 1
        return instance

    def apply_local_edit(self, edit: CollaborativeEdit) -> None:
        self.pending_edits.append(edit)
        self.content = _apply(self.content, edit)
        self.sync_state = "syncing"

    def reconcile_with(self, other: "CollaborationSession") -> ReconciliationResult:
        if self.base_content != other.base_content:
            return self._conflict(other, "documents have different base content")
        if _has_overlapping_replacements(self.pending_edits, other.pending_edits):
            return self._conflict(other, "offline edits changed the same text range")
        merged = self.base_content
        base_len = len(self.base_content)
        # Every edit carries base-relative coordinates. Sort by start position
        # (inserts before replaces at the same spot, then by collaborator for
        # determinism) and shift each span by ``offset`` — the running sum of
        # length deltas from edits already applied *before* it — so a replace no
        # longer lands on coordinates an earlier insert has since shifted.
        spans = sorted(
            (_edit_span(edit, base_len) for edit in (*self.pending_edits, *other.pending_edits)),
            key=lambda s: (s[0], s[1], 0 if s[3] else 1, s[4]),
        )
        offset = 0
        had_replace = False
        for start, end, text, is_replace, _cid in spans:
            real_start = max(0, min(len(merged), start + offset))
            real_end = max(real_start, min(len(merged), end + offset))
            merged = merged[:real_start] + text + merged[real_end:]
            offset += len(text) - (real_end - real_start)
            had_replace = had_replace or is_replace
        if had_replace:
            merged = _ensure_trailing_newline(merged)
        self.content = merged
        other.content = merged
        self.pending_edits.clear()
        other.pending_edits.clear()
        self.sync_state = "synced"
        other.sync_state = "synced"
        return ReconciliationResult(sync_state="synced")

    def _conflict(self, other: "CollaborationSession", summary: str) -> ReconciliationResult:
        self.sync_state = "conflict"
        other.sync_state = "conflict"
        path = _conflict_path(self.document_id)
        return ReconciliationResult(
            sync_state="conflict",
            conflict_copy=ConflictCopy(path=path, content=other.content),
            conflict_summary=ConflictSummary(document_id=self.document_id, summary=summary),
        )

    @staticmethod
    async def route_collaborator_proposed_action(
        session: AsyncSession,
        *,
        project_id: str,
        collaborator_id: str,
        mode: str,
        action_kind: str,
        target_ref: str,
        summary: str,
        payload: dict[str, object] | None = None,
    ) -> GateResult:
        return await ActionGate(session).govern(
            GovernedAction(
                mode=mode,
                action_kind=action_kind,
                target_kind="collaborative-document",
                target_ref=target_ref,
                trust_origin=TRUST_UNTRUSTED,
                justification_trust=TRUST_UNTRUSTED,
                project_id=project_id,
                actor=f"collaborator:{collaborator_id}",
                summary=summary,
                payload=dict(payload or {}),
            )
        )


def _edit_span(edit: CollaborativeEdit, base_len: int) -> tuple[int, int, str, bool, str]:
    """Normalize an edit to base-relative ``(start, end, text, is_replace, cid)``.

    A pure insert is a zero-width span at its position; ``insert_at is None`` means
    append at end-of-base; a replace spans its ``replace_range``.
    """
    if edit.replace_range is not None:
        start, end = edit.replace_range
        return start, end, edit.text, True, edit.collaborator_id
    if edit.insert_at is None:
        return base_len, base_len, edit.text, False, edit.collaborator_id
    return edit.insert_at, edit.insert_at, edit.text, False, edit.collaborator_id


def _apply(content: str, edit: CollaborativeEdit) -> str:
    if edit.replace_range is not None:
        start, end = edit.replace_range
        next_content = content[:start] + edit.text + content[end:]
        return _ensure_trailing_newline(next_content)
    position = len(content) if edit.insert_at is None else max(0, min(len(content), edit.insert_at))
    return content[:position] + edit.text + content[position:]


def _has_overlapping_replacements(left: list[CollaborativeEdit], right: list[CollaborativeEdit]) -> bool:
    for a in left:
        if a.replace_range is None:
            continue
        for b in right:
            if b.replace_range is None:
                continue
            if max(a.replace_range[0], b.replace_range[0]) < min(a.replace_range[1], b.replace_range[1]):
                return True
    return False


def _conflict_path(document_id: str) -> str:
    if document_id.endswith(".md"):
        return document_id[:-3] + ".conflict.md"
    return document_id + ".conflict.md"


def _ensure_trailing_newline(content: str) -> str:
    return content if content.endswith("\n") else content + "\n"
