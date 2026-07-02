"""Versioned reproducibility manifest schema (HL-QUAL-30)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from hydra.database.models import ReproducibilityManifest

SCHEMA_VERSION = "reproducibility-manifest.v1"
HASH_ALGORITHM = "sha256"

MANIFEST_REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "project_id",
    "package_version",
    "schema_version",
    "hash_algorithm",
    "source_ids",
    "sources",
    "artifacts",
    "prompts",
    "model_calls",
    "tool_calls",
    "code_version",
    "environment_version",
    "approvals",
    "checkpoints",
    "redaction_decisions",
    "run_ids",
    "created_at",
)


class ManifestValidationError(ValueError):
    """Raised when a manifest payload omits a required top-level field."""


@dataclass(frozen=True)
class ReproducibilityManifestDocument:
    id: str
    project_id: str
    package_version: str
    schema_version: str
    hash_algorithm: str
    source_ids: list[str]
    sources: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    prompts: list[dict[str, Any]] = field(default_factory=list)
    model_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    code_version: dict[str, Any] = field(default_factory=dict)
    environment_version: dict[str, Any] = field(default_factory=dict)
    approvals: list[str] = field(default_factory=list)
    checkpoints: list[str] = field(default_factory=list)
    redaction_decisions: list[dict[str, Any]] = field(default_factory=list)
    run_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ReproducibilityManifestDocument":
        missing = [field for field in MANIFEST_REQUIRED_FIELDS if field not in payload]
        if missing:
            raise ManifestValidationError(f"manifest missing required field(s): {', '.join(missing)}")
        return cls(
            id=str(payload["id"]),
            project_id=str(payload["project_id"]),
            package_version=str(payload["package_version"]),
            schema_version=str(payload["schema_version"]),
            hash_algorithm=str(payload["hash_algorithm"]),
            source_ids=[str(item) for item in payload["source_ids"]],
            sources=[dict(item) for item in payload["sources"]],
            artifacts=[dict(item) for item in payload["artifacts"]],
            prompts=[dict(item) for item in payload["prompts"]],
            model_calls=[dict(item) for item in payload["model_calls"]],
            tool_calls=[dict(item) for item in payload["tool_calls"]],
            code_version=dict(payload["code_version"]),
            environment_version=dict(payload["environment_version"]),
            approvals=[str(item) for item in payload["approvals"]],
            checkpoints=[str(item) for item in payload["checkpoints"]],
            redaction_decisions=[dict(item) for item in payload["redaction_decisions"]],
            run_ids=[str(item) for item in payload["run_ids"]],
            created_at=str(payload["created_at"]),
        )

    def validate(self) -> None:
        self.from_payload(self.public_dict())

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "package_version": self.package_version,
            "schema_version": self.schema_version,
            "hash_algorithm": self.hash_algorithm,
            "source_ids": list(self.source_ids),
            "sources": [dict(item) for item in self.sources],
            "artifacts": [dict(item) for item in self.artifacts],
            "prompts": [dict(item) for item in self.prompts],
            "model_calls": [dict(item) for item in self.model_calls],
            "tool_calls": [dict(item) for item in self.tool_calls],
            "code_version": dict(self.code_version),
            "environment_version": dict(self.environment_version),
            "approvals": list(self.approvals),
            "checkpoints": list(self.checkpoints),
            "redaction_decisions": [dict(item) for item in self.redaction_decisions],
            "run_ids": list(self.run_ids),
            "created_at": self.created_at,
        }

    def canonical_json(self) -> str:
        return json.dumps(self.public_dict(), sort_keys=True, indent=2)

    def stable_payload(self) -> dict[str, Any]:
        payload = self.public_dict()
        payload.pop("id", None)
        payload.pop("created_at", None)
        return payload

    def stable_content_hash(self) -> str:
        """Hash deterministic content, excluding volatile id/created_at wrapper fields."""
        raw = json.dumps(self.stable_payload(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return f"sha256:{hashlib.sha256(raw).hexdigest()}"

    def to_row(self, manifest_content_hash: str | None = None) -> ReproducibilityManifest:
        return ReproducibilityManifest(
            id=self.id,
            project_id=self.project_id,
            package_version=self.package_version,
            schema_version=self.schema_version,
            hash_algorithm=self.hash_algorithm,
            source_ids_json=json.dumps(self.source_ids, sort_keys=True),
            sources_json=json.dumps(self.sources, sort_keys=True),
            artifacts_json=json.dumps(self.artifacts, sort_keys=True),
            prompts_json=json.dumps(self.prompts, sort_keys=True),
            model_calls_json=json.dumps(self.model_calls, sort_keys=True),
            tool_calls_json=json.dumps(self.tool_calls, sort_keys=True),
            code_version_json=json.dumps(self.code_version, sort_keys=True),
            environment_version_json=json.dumps(self.environment_version, sort_keys=True),
            approvals_json=json.dumps(self.approvals, sort_keys=True),
            checkpoints_json=json.dumps(self.checkpoints, sort_keys=True),
            redaction_decisions_json=json.dumps(self.redaction_decisions, sort_keys=True),
            run_ids_json=json.dumps(self.run_ids, sort_keys=True),
            manifest_content_hash=manifest_content_hash or self.stable_content_hash(),
        )
