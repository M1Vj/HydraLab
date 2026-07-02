from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import Annotation, AnnotationIndexMetadata, Claim, Note, ReviewItem
from hydra.services.annotations.sidecar import (
    annotation_sidecar_path,
    external_edit_requires_reindex,
    read_sidecar_payload,
    read_sidecar_records,
    reconcile_annotation_records,
)


def _json_list(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value or [])


def _json_obj(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value or {})


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    parsed = json.loads(value)
    return [str(item) for item in parsed]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnnotationIndexer:
    def __init__(self, session: AsyncSession, project_root: str | Path):
        self.session = session
        self.project_root = Path(project_root)

    async def rebuild_from_sidecars(self, source_id: str | None = None) -> list[Annotation]:
        records = self._records_for_rebuild(source_id)
        if source_id is not None:
            await self.session.exec(delete(Annotation).where(Annotation.source_id == source_id))
        else:
            await self.session.exec(delete(Annotation))

        annotations = [self._annotation_from_record(record) for record in records]
        for annotation in annotations:
            self.session.add(annotation)
        if source_id is not None:
            await self._record_index_metadata(source_id)
        await self.session.commit()
        for annotation in annotations:
            await self.session.refresh(annotation)
        return annotations

    async def sidecar_index_stale(self, source_id: str) -> bool:
        path = annotation_sidecar_path(self.project_root, source_id)
        if not path.exists():
            return False
        metadata = await self.session.get(AnnotationIndexMetadata, source_id)
        if metadata is None:
            return True
        return metadata.sidecar_content_hash != _file_hash(path)

    async def reindex_if_external_edit(self, source_id: str, stored_hash: str, *, app_wrote_last: bool) -> list[Annotation]:
        path = annotation_sidecar_path(self.project_root, source_id)
        if not path.exists() or not external_edit_requires_reindex(stored_hash, path, app_wrote_last=app_wrote_last):
            return []
        return await self.rebuild_from_sidecars(source_id)

    async def reconcile_records(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        result = reconcile_annotation_records(left, right)
        if not result.conflict:
            return result.record

        review_item = ReviewItem(
            item_type="annotation-conflict",
            title=f"Resolve annotation conflict on page {left.get('page', '?')}",
            summary="Two annotation edits have the same revision and different content hashes. Choose the authoritative record.",
            origin_type="annotation",
            origin_id=str(left["sidecar_record_id"]),
            target_type="annotation",
            target_id=str(left["sidecar_record_id"]),
            payload_json=json.dumps({"left": left, "right": right}, sort_keys=True),
        )
        self.session.add(review_item)
        await self.session.commit()
        return result.record

    async def create_or_suggest_claim(self, sidecar_record_id: str, *, auto_create: bool) -> dict[str, Any]:
        annotation = await self.session.get(Annotation, sidecar_record_id)
        if annotation is None:
            raise ValueError(f"annotation not found: {sidecar_record_id}")

        if not auto_create:
            review_item = ReviewItem(
                item_type="annotation-claim-suggestion",
                title="Review claim suggested from PDF highlight",
                summary=annotation.text,
                origin_type="annotation",
                origin_id=annotation.sidecar_record_id,
                target_type="claim",
                payload_json=json.dumps({"annotation_id": annotation.sidecar_record_id, "text": annotation.text}, sort_keys=True),
            )
            self.session.add(review_item)
            await self.session.commit()
            await self.session.refresh(review_item)
            return {
                "created_claim": None,
                "review_item": {
                    "id": review_item.id,
                    "item_type": review_item.item_type,
                    "origin_id": review_item.origin_id,
                },
            }

        claim = Claim(
            text=annotation.text,
            location_type="source",
            location_id=annotation.source_id,
            status="draft",
            trust_origin="user",
        )
        linked_claim_ids = _parse_json_list(annotation.linked_claim_ids)
        self.session.add(claim)
        await self.session.commit()
        await self.session.refresh(claim)
        if claim.id not in linked_claim_ids:
            linked_claim_ids.append(claim.id)
        annotation.linked_claim_ids = json.dumps(linked_claim_ids)
        annotation.updated_at = _utcnow()
        self.session.add(annotation)
        await self.session.commit()
        return {
            "created_claim": {"id": claim.id, "status": claim.status, "text": claim.text},
            "review_item": None,
        }

    async def scan_referential_integrity(self) -> list[dict[str, str]]:
        findings: list[dict[str, str]] = []
        annotations = (await self.session.exec(select(Annotation))).all()
        for annotation in annotations:
            for claim_id in _parse_json_list(annotation.linked_claim_ids):
                if await self.session.get(Claim, claim_id) is None:
                    findings.append(await self._record_broken_link(annotation, "claim", claim_id))
            for note_id in _parse_json_list(annotation.linked_note_ids):
                if await self.session.get(Note, note_id) is None:
                    findings.append(await self._record_broken_link(annotation, "note", note_id))
        return findings

    def _records_for_rebuild(self, source_id: str | None) -> list[dict[str, Any]]:
        if source_id is not None:
            return read_sidecar_records(self.project_root, source_id)

        records: list[dict[str, Any]] = []
        sidecar_root = self.project_root / "sources" / "papers" / "annotations"
        for path in sorted(sidecar_root.glob("*.annotations.json")):
            payload = read_sidecar_payload(path)
            records.extend(payload.get("records", []))
        return records

    async def _record_index_metadata(self, source_id: str) -> None:
        path = annotation_sidecar_path(self.project_root, source_id)
        if not path.exists():
            return
        metadata = await self.session.get(AnnotationIndexMetadata, source_id)
        if metadata is None:
            metadata = AnnotationIndexMetadata(source_id=source_id, sidecar_path=str(path.relative_to(self.project_root)))
        metadata.sidecar_content_hash = _file_hash(path)
        metadata.indexed_at = _utcnow()
        self.session.add(metadata)

    def _annotation_from_record(self, record: dict[str, Any]) -> Annotation:
        return Annotation(
            sidecar_record_id=str(record["sidecar_record_id"]),
            source_id=str(record["source_id"]),
            page=int(record.get("page") or 1),
            text=str(record.get("text") or ""),
            quad_points=_json_list(record.get("quad_points")),
            bbox=_json_obj(record.get("bbox")),
            type=str(record.get("type") or "highlight"),
            linked_claim_ids=_json_list(record.get("linked_claim_ids")),
            linked_note_ids=_json_list(record.get("linked_note_ids")),
            color=record.get("color"),
            rev=int(record.get("rev") or 1),
            content_hash=str(record.get("content_hash") or ""),
            link_state=str(record.get("link_state") or "live"),
            trust_origin=str(record.get("trust_origin") or "user"),
        )

    async def _record_broken_link(self, annotation: Annotation, target_type: str, missing_id: str) -> dict[str, str]:
        finding = {
            "annotation_id": annotation.sidecar_record_id,
            "missing_type": target_type,
            "missing_id": missing_id,
        }
        existing = (
            await self.session.exec(
                select(ReviewItem).where(
                    ReviewItem.item_type == "annotation-broken-link",
                    ReviewItem.origin_id == annotation.sidecar_record_id,
                    ReviewItem.target_type == target_type,
                    ReviewItem.target_id == missing_id,
                )
            )
        ).first()
        if existing is None:
            self.session.add(
                ReviewItem(
                    item_type="annotation-broken-link",
                    title=f"Repair missing {target_type} link",
                    summary=f"Annotation link target no longer exists: {missing_id}",
                    origin_type="annotation",
                    origin_id=annotation.sidecar_record_id,
                    target_type=target_type,
                    target_id=missing_id,
                    payload_json=json.dumps(finding, sort_keys=True),
                )
            )
            await self.session.commit()
        return finding


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
