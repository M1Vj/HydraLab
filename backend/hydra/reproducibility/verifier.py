"""Manifest verifier for bundle hashes and references (HL-QUAL-36)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import AgentRun, Citation, ExperimentRun, Source, SourceTombstone


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    hash_mismatches: list[str] = field(default_factory=list)
    dangling_ids: list[str] = field(default_factory=list)
    resolved_soft_deleted_or_merged: list[dict[str, Any]] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "hash_mismatches": list(self.hash_mismatches),
            "dangling_ids": list(self.dangling_ids),
            "resolved_soft_deleted_or_merged": [dict(item) for item in self.resolved_soft_deleted_or_merged],
        }


class ManifestVerifier:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def verify(self, bundle_path_or_manifest: str | Path | dict[str, Any]) -> VerificationResult:
        bundle_dir, manifest = _load_manifest(bundle_path_or_manifest)
        mismatches = _hash_mismatches(bundle_dir, manifest)
        dangling: list[str] = []
        resolved: list[dict[str, Any]] = []
        for source_id in manifest.get("source_ids", []):
            resolved_id, note = await self._resolve_source(str(source_id))
            if resolved_id is None:
                dangling.append(str(source_id))
            elif note is not None:
                resolved.append(note)
        for source in manifest.get("sources", []):
            for citation in source.get("citations", []):
                citation_id = str(citation.get("citation_id") or "")
                if citation_id and await self.session.get(Citation, citation_id) is None:
                    dangling.append(citation_id)
        for run_id in manifest.get("run_ids", []):
            if await self.session.get(AgentRun, str(run_id)) is None and await self.session.get(ExperimentRun, str(run_id)) is None:
                dangling.append(str(run_id))
        dangling = sorted(dict.fromkeys(dangling))
        return VerificationResult(ok=not mismatches and not dangling, hash_mismatches=mismatches, dangling_ids=dangling, resolved_soft_deleted_or_merged=resolved)

    async def _resolve_source(self, source_id: str) -> tuple[str | None, dict[str, Any] | None]:
        current = source_id
        seen: set[str] = set()
        note: dict[str, Any] | None = None
        while current not in seen:
            seen.add(current)
            source = await self.session.get(Source, current)
            if source is not None:
                if source.trashed:
                    note = {"id": source_id, "resolved_id": source.id, "state": "soft-deleted"}
                elif current != source_id:
                    note = {"id": source_id, "resolved_id": source.id, "state": "merged"}
                return source.id, note
            tombstone = await self.session.get(SourceTombstone, current)
            if tombstone is None:
                return None, None
            current = tombstone.survivor_id
            note = {"id": source_id, "resolved_id": current, "state": "merged"}
        return None, None


def _load_manifest(value: str | Path | dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    if isinstance(value, dict):
        return Path("."), value
    path = Path(value)
    if path.is_dir():
        return path, json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    return path.parent, json.loads(path.read_text(encoding="utf-8"))


def _hash_mismatches(bundle_dir: Path, manifest: dict[str, Any]) -> list[str]:
    mismatches = []
    for artifact in manifest.get("artifacts", []):
        relpath = str(artifact.get("path") or "")
        expected = str(artifact.get("content_hash") or "")
        path = bundle_dir / "artifacts" / relpath
        if not path.exists() or _file_hash(path) != expected:
            mismatches.append(relpath)
    return mismatches


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
