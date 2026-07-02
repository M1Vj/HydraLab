from __future__ import annotations

import hashlib
import json
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hydra.storage.sidecar import SidecarConflictResult, external_edit_forces_reindex, resolve_sidecar_conflict

SIDECAR_SCHEMA_VERSION = 1
_HASH_EXCLUDED_FIELDS = {"content_hash", "created_at", "updated_at", "rev"}
_SAFE_SOURCE_ID = re.compile(r"[^A-Za-z0-9_.-]+")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_source_id(source_id: str) -> str:
    return _SAFE_SOURCE_ID.sub("_", source_id).strip("._") or hashlib.sha256(source_id.encode()).hexdigest()[:16]


def annotation_sidecar_path(project_root: str | Path, source_id: str) -> Path:
    return Path(project_root) / "sources" / "papers" / "annotations" / f"{_safe_source_id(source_id)}.annotations.json"


def to_normalized_quad_points(rect: dict[str, float], *, page_width: float, page_height: float) -> list[float]:
    if page_width <= 0 or page_height <= 0:
        raise ValueError("page dimensions must be positive")
    left = float(rect["left"])
    top = float(rect["top"])
    right = left + float(rect["width"])
    bottom = top + float(rect["height"])
    points = [
        left / page_width,
        top / page_height,
        right / page_width,
        top / page_height,
        right / page_width,
        bottom / page_height,
        left / page_width,
        bottom / page_height,
    ]
    return [round(max(0.0, min(1.0, point)), 6) for point in points]


def to_viewport_rect(quad_points: list[float], *, page_width: float, page_height: float, scale: float) -> dict[str, int]:
    if len(quad_points) != 8:
        raise ValueError("quad_points must contain 8 normalized numbers")
    xs = [float(quad_points[index]) for index in range(0, 8, 2)]
    ys = [float(quad_points[index]) for index in range(1, 8, 2)]
    left = min(xs) * page_width * scale
    top = min(ys) * page_height * scale
    width = (max(xs) - min(xs)) * page_width * scale
    height = (max(ys) - min(ys)) * page_height * scale
    return {
        "left": round(left),
        "top": round(top),
        "width": round(width),
        "height": round(height),
    }


def _canonical_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in record.items() if key not in _HASH_EXCLUDED_FIELDS}


def compute_record_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(_canonical_record(record), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bbox_from_quad_points(quad_points: list[float]) -> dict[str, float]:
    if len(quad_points) != 8:
        raise ValueError("quad_points must contain 8 normalized numbers")
    xs = [float(quad_points[index]) for index in range(0, 8, 2)]
    ys = [float(quad_points[index]) for index in range(1, 8, 2)]
    return {
        "left": round(min(xs), 6),
        "top": round(min(ys), 6),
        "width": round(max(xs) - min(xs), 6),
        "height": round(max(ys) - min(ys), 6),
    }


def create_annotation_record(
    *,
    source_id: str,
    page: int,
    text: str,
    quad_points: list[float],
    annotation_type: str = "highlight",
    linked_claim_ids: list[str] | None = None,
    linked_note_ids: list[str] | None = None,
    color: str = "yellow",
    sidecar_record_id: str | None = None,
) -> dict[str, Any]:
    timestamp = _now_iso()
    record = {
        "sidecar_record_id": sidecar_record_id or str(uuid.uuid4()),
        "source_id": source_id,
        "page": page,
        "text": text,
        "quad_points": [float(point) for point in quad_points],
        "bbox": _bbox_from_quad_points(quad_points),
        "type": annotation_type,
        "linked_claim_ids": linked_claim_ids or [],
        "linked_note_ids": linked_note_ids or [],
        "color": color,
        "link_state": "live",
        "trust_origin": "user",
        "created_at": timestamp,
        "updated_at": timestamp,
        "rev": 1,
    }
    record["content_hash"] = compute_record_hash(record)
    return record


def _sidecar_payload(source_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "source_id": source_id,
        "records": records,
    }


def write_sidecar_records(project_root: str | Path, source_id: str, records: list[dict[str, Any]]) -> Path:
    path = annotation_sidecar_path(project_root, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sidecar_payload(source_id, records)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return path


def read_sidecar_records(project_root: str | Path, source_id: str) -> list[dict[str, Any]]:
    path = annotation_sidecar_path(project_root, source_id)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError(f"annotation sidecar records must be a list: {path}")
    return records


def read_sidecar_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def reconcile_annotation_records(left: dict[str, Any], right: dict[str, Any]) -> SidecarConflictResult:
    return resolve_sidecar_conflict(left, right)


def external_edit_requires_reindex(stored_hash: str, path: Path, *, app_wrote_last: bool) -> bool:
    sidecar_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    return external_edit_forces_reindex(stored_hash, sidecar_hash, app_wrote_last)
