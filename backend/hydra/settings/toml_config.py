from __future__ import annotations

import copy
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomli_w


CURRENT_SETTINGS_VERSION = 1
HYDRALAB_VERSION = "0.1.0"
REQUIRED_SETTINGS_SECTIONS = [
    "schema",
    "general",
    "appearance",
    "workspace",
    "browser",
    "indexing",
    "review_inbox",
    "memory",
    "assistant",
    "providers",
    "skills",
    "citations",
    "writing",
    "git",
    "exports",
    "privacy",
    "diagnostics",
]


class SettingsValidationError(ValueError):
    pass


@dataclass
class LoadedSettings:
    path: Path
    data: dict[str, Any]


def default_settings() -> dict[str, Any]:
    data = {section: {} for section in REQUIRED_SETTINGS_SECTIONS}
    data["schema"] = {"version": CURRENT_SETTINGS_VERSION, "hydralab_version": HYDRALAB_VERSION}
    data["general"] = {"offline_only": False}
    data["browser"] = {
        "local_capture_enabled": False,
        "allowlist": [],
        "blocklist": [],
        "browser_page_text_to_provider": False,
    }
    data["indexing"] = {
        "auto_index_categories": ["sources", "knowledge", "work", "writing", "outputs"],
        "consent_required_categories": [
            "code-folder",
            "browser-history",
            "chat-logs",
            "agent-memory",
            "large-generated",
        ],
        "ignored_paths": [".git", ".env", ".hydralab/cache", ".hydralab/temp"],
        "queue": {"max_parallel_jobs": 1, "retry_limit": 3},
    }
    data["review_inbox"] = {"enabled_item_types": ["broken-link", "conflict", "reindex"]}
    data["assistant"] = {"mode": "passive", "provider_routing_profile": "manual"}
    data["providers"] = {"routing_policy": "manual", "accounts": {}}
    data["privacy"] = {
        "offline_only": False,
        "scholarly_apis_enabled": True,
        "g3_provider_send": False,
        "provider_send_allowlist": ["active_file", "selection", "explicit_attachment"],
        "provider_send_opt_ins": {
            "full_notes_corpus": False,
            "all_pdfs_extracted_text": False,
            "saved_chats": False,
            "agent_run_logs": False,
            "project_metadata": False,
            "browser_page_text": False,
        },
    }
    return data


def load_settings(path: Path) -> LoadedSettings:
    path = Path(path)
    if not path.exists():
        data = default_settings()
        save_settings(path, data)
        return LoadedSettings(path=path, data=data)

    with path.open("rb") as fh:
        data = tomllib.load(fh)
    validate_settings(data)
    migrated = migrate_settings(copy.deepcopy(data))
    validate_settings(migrated)
    return LoadedSettings(path=path, data=migrated)


def save_settings(path: Path, data: dict[str, Any], validate: bool = True) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = copy.deepcopy(data)
    if validate:
        payload = migrate_settings(payload)
        validate_settings(payload)
    path.write_text(tomli_w.dumps(payload))


def migrate_settings(data: dict[str, Any]) -> dict[str, Any]:
    for section, defaults in default_settings().items():
        data.setdefault(section, copy.deepcopy(defaults))
    schema = data.setdefault("schema", {})
    schema.setdefault("version", CURRENT_SETTINGS_VERSION)
    schema.setdefault("hydralab_version", HYDRALAB_VERSION)
    return data


def validate_settings(data: dict[str, Any]) -> None:
    missing = [section for section in REQUIRED_SETTINGS_SECTIONS if section not in data]
    if missing:
        names = ", ".join(f"[{section}]" for section in missing)
        raise SettingsValidationError(f"Missing required settings section(s): {names}")
    for section in REQUIRED_SETTINGS_SECTIONS:
        if not isinstance(data[section], dict):
            raise SettingsValidationError(f"[{section}] must be a TOML table")
    providers = data.get("providers", {})
    serialized = repr(providers).lower()
    for secret_word in ("api_key", "token", "secret"):
        if secret_word in serialized and "secret_ref" not in serialized:
            raise SettingsValidationError("[providers] may store secret references only")
