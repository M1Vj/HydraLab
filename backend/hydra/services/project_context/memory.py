from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import ContextFileChange, ReviewItem
from hydra.services.project_context.loaders import GLOBAL_CONTEXT_FILES, PROJECT_CONTEXT_FILE

TRUST_UNTRUSTED = "untrusted-external"

# Categories that MUST NOT auto-promote under any setting (Section 11 / 28.5).
REVIEW_REQUIRED_CATEGORIES = {
    "research_conclusion",
    "claim_support_status",
    "literature_summary",
    "manuscript_text",
    "project_direction",
    "user_identity",
    "user_preference",
}
# Non-substantive categories eligible for opt-in low-risk auto-promotion.
LOW_RISK_CATEGORIES = {
    "source_metadata_cleanup",
    "tag_normalization",
    "duplicate_low_risk_index_note",
    "organization_update",
}
# Facts that must be written to a context file immediately rather than batched.
CRITICAL_CATEGORIES = {"user_identity", "project_direction"}

DEFAULT_CONDENSE_THRESHOLD_KB = 32


@dataclass
class UpdateResult:
    written: bool
    file: str
    timing: str
    criticality: str
    change_id: Optional[str] = None
    checkpoint_ref: Optional[str] = None
    review_item: Optional[dict[str, Any]] = None
    reason: str = ""


class ContextFileMemory:
    def __init__(self, session: AsyncSession, project_root: Path, profile_root: Path, profile_id: str = "default") -> None:
        self.session = session
        self.project_root = Path(project_root)
        self.profile_root = Path(profile_root)
        self.profile_id = profile_id

    # ------------------------------------------------------------------ helpers
    def _resolve_path(self, file: str) -> Path:
        if file == PROJECT_CONTEXT_FILE:
            return self.project_root / file
        if file in GLOBAL_CONTEXT_FILES:
            return self.profile_root / file
        raise ValueError(f"unknown context file: {file}")

    def _checkpoint_ledger_path(self) -> Path:
        return self.project_root / ".hydralab" / "checkpoints" / "hydra-md.json"

    def _read_checkpoints(self) -> list[dict[str, Any]]:
        path = self._checkpoint_ledger_path()
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def create_checkpoint(self, *, summary: str = "") -> str:
        """Create a Git/checkpoint history entry for HYDRA.md (never an archive file)."""
        path = self.project_root / PROJECT_CONTEXT_FILE
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        checkpoint_id = f"chk_{int(time.time() * 1000)}"
        entries = self._read_checkpoints()
        entries.append({"id": checkpoint_id, "summary": summary, "snapshot": content, "created_at": time.time()})
        ledger = self._checkpoint_ledger_path()
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        if (self.project_root / ".git").exists():
            subprocess.run(["git", "add", PROJECT_CONTEXT_FILE], cwd=self.project_root, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(
                ["git", *self._git_identity_flags(), "commit", "-m", f"checkpoint(HYDRA.md): {summary or checkpoint_id}", "--", PROJECT_CONTEXT_FILE],
                cwd=self.project_root,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return checkpoint_id

    def _git_identity_flags(self) -> list[str]:
        """Fallback commit identity so HYDRA.md checkpoints record even when the
        machine has no git identity configured (fresh machine / bare CI)."""
        def _cfg(key: str) -> str:
            return subprocess.run(
                ["git", "config", key], cwd=self.project_root,
                capture_output=True, text=True, check=False,
            ).stdout.strip()
        if _cfg("user.email") and _cfg("user.name"):
            return []
        return ["-c", "user.name=HydraLab", "-c", "user.email=hydralab@localhost"]

    def list_checkpoints(self, file: str = PROJECT_CONTEXT_FILE) -> list[dict[str, Any]]:
        if file != PROJECT_CONTEXT_FILE:
            return []
        return self._read_checkpoints()

    async def _log_change(
        self,
        *,
        file: str,
        change_type: str,
        timing: str,
        criticality: str,
        trust_level: str,
        provenance: str,
        summary: str,
        checkpoint_ref: Optional[str],
        project_id: Optional[str],
    ) -> ContextFileChange:
        change = ContextFileChange(
            project_id=project_id,
            profile_id=self.profile_id,
            file=file,
            change_type=change_type,
            timing=timing,
            criticality=criticality,
            trust_level=trust_level,
            provenance=provenance,
            summary=summary,
            checkpoint_ref=checkpoint_ref,
            logs_only=file in GLOBAL_CONTEXT_FILES,
        )
        self.session.add(change)
        await self.session.commit()
        await self.session.refresh(change)
        return change

    # ------------------------------------------------------------------ writes
    async def record_update(
        self,
        *,
        file: str,
        new_content: str,
        category: str = "organization_update",
        provenance: str = "assistant",
        trust_level: str = "trusted",
        project_id: Optional[str] = None,
        summary: str = "",
    ) -> UpdateResult:
        """Apply a hybrid, logged context-file update.

        Untrusted-provenance content is NEVER auto-written into a context file; it is
        routed to the Review Inbox instead (HL-TRUST-02/03).
        """
        if trust_level == TRUST_UNTRUSTED or provenance == TRUST_UNTRUSTED:
            review = await self.route_memory_candidate(
                fact=summary or new_content[:280],
                destination=file,
                category=category,
                confidence=0.0,
                trust_origin=TRUST_UNTRUSTED,
                project_id=project_id,
                source_ref=summary or "untrusted-external",
            )
            return UpdateResult(
                written=False,
                file=file,
                timing="n/a",
                criticality="n/a",
                review_item=review,
                reason="untrusted-external content cannot auto-write a context file",
            )

        criticality = "critical" if category in CRITICAL_CATEGORIES else "normal"
        timing = "immediate" if criticality == "critical" else "batched"
        path = self._resolve_path(file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding="utf-8")

        checkpoint_ref: Optional[str] = None
        if file == PROJECT_CONTEXT_FILE:
            # HYDRA.md is Git/checkpoint-backed. Critical -> immediate checkpoint.
            if criticality == "critical":
                checkpoint_ref = self.create_checkpoint(summary=summary or f"critical {category}")
            else:
                checkpoint_ref = self.create_checkpoint(summary=summary or f"batched {category}")

        change = await self._log_change(
            file=file,
            change_type="update",
            timing=timing,
            criticality=criticality,
            trust_level=trust_level,
            provenance=provenance,
            summary=summary or f"{category} update",
            checkpoint_ref=checkpoint_ref,
            project_id=project_id,
        )
        return UpdateResult(
            written=True,
            file=file,
            timing=timing,
            criticality=criticality,
            change_id=change.id,
            checkpoint_ref=checkpoint_ref,
        )

    async def manual_edit(self, *, file: str, new_content: str, project_id: Optional[str] = None) -> UpdateResult:
        path = self._resolve_path(file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding="utf-8")
        checkpoint_ref = None
        if file == PROJECT_CONTEXT_FILE:
            checkpoint_ref = self.create_checkpoint(summary="manual edit")
        change = await self._log_change(
            file=file,
            change_type="manual_edit",
            timing="immediate",
            criticality="normal",
            trust_level="trusted",
            provenance="user",
            summary="manual user edit",
            checkpoint_ref=checkpoint_ref,
            project_id=project_id,
        )
        return UpdateResult(written=True, file=file, timing="immediate", criticality="normal", change_id=change.id, checkpoint_ref=checkpoint_ref)

    def _threshold_bytes(self, condense_threshold_kb: int) -> int:
        return max(1, condense_threshold_kb) * 1024

    async def condense(
        self,
        *,
        file: str,
        condensed_content: str,
        condense_threshold_kb: int = DEFAULT_CONDENSE_THRESHOLD_KB,
        project_id: Optional[str] = None,
    ) -> UpdateResult:
        """Condense an oversized context file.

        HYDRA.md: create a Git/checkpoint entry BEFORE writing condensed content.
        Global files: write a log entry only. Never create archive files/folders.
        """
        path = self._resolve_path(file)
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if len(current.encode("utf-8")) < self._threshold_bytes(condense_threshold_kb):
            return UpdateResult(written=False, file=file, timing="n/a", criticality="normal", reason="below condense threshold")

        checkpoint_ref: Optional[str] = None
        if file == PROJECT_CONTEXT_FILE:
            checkpoint_ref = self.create_checkpoint(summary="pre-condense checkpoint")
        # Write condensed content in place (no archive sidecar).
        path.write_text(condensed_content, encoding="utf-8")
        change = await self._log_change(
            file=file,
            change_type="condense",
            timing="immediate",
            criticality="normal",
            trust_level="trusted",
            provenance="assistant",
            summary="condense",
            checkpoint_ref=checkpoint_ref,
            project_id=project_id,
        )
        return UpdateResult(written=True, file=file, timing="immediate", criticality="normal", change_id=change.id, checkpoint_ref=checkpoint_ref)

    # --------------------------------------------------------- memory candidates
    async def route_memory_candidate(
        self,
        *,
        fact: str,
        destination: str,
        category: str,
        confidence: float,
        source_ref: str = "",
        trust_origin: str = "trusted",
        project_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a review-first memory candidate in the unified Review Inbox."""
        item = ReviewItem(
            project_id=project_id,
            item_type="memory-candidate",
            title=f"Remember: {fact[:80]}",
            summary=fact,
            origin_type=trust_origin,
            origin_id=source_ref or None,
            target_type="context-file" if destination in (*GLOBAL_CONTEXT_FILES, PROJECT_CONTEXT_FILE) else "memory",
            target_id=destination,
            payload_json=json.dumps(
                {
                    "fact": fact,
                    "source_ref": source_ref,
                    "destination": destination,
                    "confidence": confidence,
                    "category": category,
                    "trust_origin": trust_origin,
                    "never_remember": False,
                },
                sort_keys=True,
            ),
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return {
            "id": item.id,
            "item_type": item.item_type,
            "title": item.title,
            "summary": item.summary,
            "trust_origin": trust_origin,
            "origin_id": item.origin_id,
            "target_id": item.target_id,
            "payload": json.loads(item.payload_json),
            "status": item.status,
        }

    async def promote_candidate(
        self,
        *,
        fact: str,
        category: str,
        destination: str,
        confidence: float = 0.5,
        auto_promote_low_risk: bool = False,
        trust_origin: str = "trusted",
        source_ref: str = "",
        project_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Apply the review-first promotion policy.

        Review-required categories never auto-promote. Low-risk categories auto-promote
        only when the setting is enabled AND the source is trusted; everything else
        routes to the Review Inbox.
        """
        is_low_risk = category in LOW_RISK_CATEGORIES and category not in REVIEW_REQUIRED_CATEGORIES
        can_auto = auto_promote_low_risk and is_low_risk and trust_origin != TRUST_UNTRUSTED
        if not can_auto:
            review = await self.route_memory_candidate(
                fact=fact,
                destination=destination,
                category=category,
                confidence=confidence,
                source_ref=source_ref,
                trust_origin=trust_origin,
                project_id=project_id,
            )
            return {"auto_promoted": False, "review_item": review}

        change = await self._log_change(
            file=destination if destination in (*GLOBAL_CONTEXT_FILES, PROJECT_CONTEXT_FILE) else "MEMORY.md",
            change_type="auto-promote",
            timing="batched",
            criticality="normal",
            trust_level="trusted",
            provenance="assistant",
            summary=f"auto-promoted low-risk: {fact[:120]}",
            checkpoint_ref=None,
            project_id=project_id,
        )
        return {"auto_promoted": True, "reversible": True, "change_id": change.id, "category": category}

    async def list_changes(self, *, project_id: Optional[str] = None, file: Optional[str] = None) -> list[dict[str, Any]]:
        q = select(ContextFileChange)
        if file:
            q = q.where(ContextFileChange.file == file)
        q = q.order_by(ContextFileChange.created_at.desc())
        rows = (await self.session.exec(q)).all()
        result = []
        for row in rows:
            if project_id and row.project_id not in (None, project_id) and row.file != PROJECT_CONTEXT_FILE:
                continue  # row belongs to a different project — never leak it across projects
            result.append(
                {
                    "id": row.id,
                    "file": row.file,
                    "change_type": row.change_type,
                    "timing": row.timing,
                    "criticality": row.criticality,
                    "trust_level": row.trust_level,
                    "provenance": row.provenance,
                    "summary": row.summary,
                    "checkpoint_ref": row.checkpoint_ref,
                    "logs_only": row.logs_only,
                    "recovery": "logs-only" if row.file in GLOBAL_CONTEXT_FILES else "git-checkpoint",
                    "created_at": row.created_at.timestamp(),
                }
            )
        return result
