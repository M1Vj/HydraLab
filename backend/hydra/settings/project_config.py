from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


CURRENT_PROJECT_SCHEMA_VERSION = 2
HYDRALAB_VERSION = "0.1.0"
REQUIRED_PROJECT_FIELDS = [
    "schema_version",
    "project_id",
    "name",
    "description",
    "created_at",
    "updated_at",
    "hydralab_version",
    "project_type",
    "domain",
    "default_citation_style",
    "default_manuscript_profile",
    "folders",
    "features",
    "privacy",
    "browser",
    "sources",
    "writing",
    "git",
    "custom_metadata",
]
FOLDER_ROLE_FIELDS = ["path", "created", "created_at", "managed_by", "purpose", "index_policy", "git_policy"]


class ProjectConfigValidationError(ValueError):
    pass


@dataclass
class LoadedProjectConfig:
    path: Path
    data: dict[str, Any]


def _yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_project_config(project_id: str, name: str) -> dict[str, Any]:
    ts = now_iso()
    return {
        "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
        "project_id": project_id,
        "name": name,
        "description": "",
        "created_at": ts,
        "updated_at": ts,
        "hydralab_version": HYDRALAB_VERSION,
        "project_type": "research",
        "domain": "general",
        "default_citation_style": "apa",
        "default_manuscript_profile": "default",
        "folders": {
            "sources": folder_role("sources/", True, "Source library"),
            "knowledge": folder_role("knowledge/", True, "Knowledge base"),
            "work": folder_role("work/", True, "Research work"),
            "writing": folder_role("writing/", True, "Draft sources"),
            "outputs": folder_role("outputs/", True, "Exports and handoffs"),
        },
        "features": {},
        "privacy": {},
        "browser": {},
        "sources": {},
        "writing": {},
        "git": {"enabled": True},
        "custom_metadata": {},
    }


def folder_role(path: str, created: bool, purpose: str, index_policy: str = "indexed", git_policy: str = "tracked") -> dict[str, Any]:
    return {
        "path": path,
        "created": created,
        "created_at": now_iso() if created else None,
        "managed_by": "hydralab",
        "purpose": purpose,
        "index_policy": index_policy,
        "git_policy": git_policy,
    }


def load_project_config(path: Path) -> LoadedProjectConfig:
    path = Path(path)
    data = _yaml().load(path.read_text()) or {}
    migrated = migrate_project_config(data)
    validate_project_config(migrated)
    save_project_config(path, migrated)
    return LoadedProjectConfig(path=path, data=dict(migrated))


def save_project_config(path: Path, data: dict[str, Any]) -> None:
    validate_project_config(data)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        _yaml().dump(data, fh)


def migrate_project_config(data: dict[str, Any]) -> dict[str, Any]:
    version = int(data.get("schema_version", 1))
    if version < 2:
        data.setdefault("default_manuscript_profile", "default")
        data["schema_version"] = 2
    data.setdefault("hydralab_version", HYDRALAB_VERSION)
    for field in REQUIRED_PROJECT_FIELDS:
        if field not in data:
            if field in {"folders", "features", "privacy", "browser", "sources", "writing", "git", "custom_metadata"}:
                data[field] = {}
            elif field == "default_manuscript_profile":
                data[field] = "default"
            else:
                data[field] = ""
    return data


def validate_project_config(data: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_PROJECT_FIELDS if field not in data]
    if missing:
        raise ProjectConfigValidationError(f"Missing project.yaml fields: {', '.join(missing)}")
    if not isinstance(data["folders"], dict):
        raise ProjectConfigValidationError("project.yaml folders must be a mapping")
    for role, record in data["folders"].items():
        if not isinstance(record, dict):
            raise ProjectConfigValidationError(f"folders.{role} must be a mapping")
        missing_fields = [field for field in FOLDER_ROLE_FIELDS if field not in record]
        if missing_fields:
            raise ProjectConfigValidationError(f"folders.{role} missing: {', '.join(missing_fields)}")
