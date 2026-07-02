from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

_yaml = YAML(typ="safe")

REQUIRED_FRONT_MATTER = [
    "id",
    "name",
    "version",
    "scope",
    "description",
    "enabled_by_default",
    "allowed_capabilities",
    "risk_level",
    "requires_approval",
    "tags",
]
REQUIRED_BODY_SECTIONS = [
    "# Purpose",
    "# When To Use",
    "# Inputs",
    "# Workflow",
    "# Outputs",
    "# Safety",
    "# References",
]
VALID_SCOPES = {"builtin", "global", "project"}
PLUGIN_MANIFEST_NAMES = {"plugin.json", "manifest.json", "marketplace.json", "package.json"}
PLUGIN_REJECTION_MESSAGE = "plugins not supported in Phase 1"


@dataclass
class LoadedSkill:
    id: str
    name: str
    scope: str
    path: str
    enabled: bool
    risk_level: str
    requires_approval: bool
    description: str = ""
    version: str = ""
    tags: list[str] = field(default_factory=list)
    allowed_capabilities: list[str] = field(default_factory=list)
    enabled_by_default: bool = False
    disabled_reason: str | None = None
    front_matter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    edited: bool = False

    def descriptor(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "description": self.description, "scope": self.scope}

    def to_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "scope": self.scope,
            "path": self.path,
            "enabled": self.enabled,
            "risk_level": self.risk_level,
            "requires_approval": self.requires_approval,
            "description": self.description,
            "version": self.version,
            "tags": self.tags,
            "allowed_capabilities": self.allowed_capabilities,
            "disabled_reason": self.disabled_reason,
            "body": self.body,
            "edited": self.edited,
            "restorable": self.scope == "builtin",
        }


def parse_skill_file(text: str) -> tuple[dict[str, Any], str]:
    """Split a Markdown-with-YAML-front-matter skill file into (front_matter, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    front_matter = _yaml.load(io.StringIO(parts[1])) or {}
    body = parts[2]
    if not isinstance(front_matter, dict):
        front_matter = {}
    return front_matter, body


def validate_skill(front_matter: dict[str, Any], body: str, *, expected_scope: str | None = None) -> str | None:
    """Return a disable reason if invalid, else None."""
    missing_fields = [key for key in REQUIRED_FRONT_MATTER if key not in front_matter]
    if missing_fields:
        return f"missing required front matter: {', '.join(missing_fields)}"
    scope = str(front_matter.get("scope"))
    if scope not in VALID_SCOPES:
        return f"invalid scope: {scope}"
    if expected_scope and scope != expected_scope:
        return f"scope mismatch: declared {scope} in {expected_scope} folder"
    missing_sections = [section for section in REQUIRED_BODY_SECTIONS if section not in body]
    if missing_sections:
        return f"missing required section: {missing_sections[0]}"
    return None


def _skill_from_text(
    text: str, path: Path, expected_scope: str, *, fallback_stem: str | None = None, edited: bool = False
) -> LoadedSkill:
    front_matter, body = parse_skill_file(text)
    reason = validate_skill(front_matter, body, expected_scope=expected_scope)
    skill_id = str(front_matter.get("id") or fallback_stem or path.stem)
    enabled_default = bool(front_matter.get("enabled_by_default", False))
    return LoadedSkill(
        id=skill_id,
        name=str(front_matter.get("name") or skill_id),
        scope=str(front_matter.get("scope") or expected_scope),
        path=str(path),
        enabled=reason is None and enabled_default,
        risk_level=str(front_matter.get("risk_level") or "unknown"),
        requires_approval=bool(front_matter.get("requires_approval", True)),
        description=str(front_matter.get("description") or ""),
        version=str(front_matter.get("version") or ""),
        tags=list(front_matter.get("tags") or []),
        allowed_capabilities=list(front_matter.get("allowed_capabilities") or []),
        enabled_by_default=enabled_default,
        disabled_reason=reason,
        front_matter=front_matter,
        body=body,
        edited=edited,
    )


def _skill_from_file(path: Path, expected_scope: str) -> LoadedSkill:
    return _skill_from_text(path.read_text(encoding="utf-8"), path, expected_scope)


@dataclass
class SkillRegistry:
    skills: list[LoadedSkill] = field(default_factory=list)
    rejected_plugins: list[dict[str, str]] = field(default_factory=list)

    def enabled_descriptors(self) -> list[dict[str, Any]]:
        return [s.descriptor() for s in self.skills if s.enabled]

    def get(self, skill_id: str) -> LoadedSkill | None:
        return next((s for s in self.skills if s.id == skill_id), None)


def builtin_skills_dir() -> Path:
    return Path(__file__).resolve().parent / "builtin"


def _state_file(state_dir: Path) -> Path:
    return Path(state_dir) / "skills_state.json"


def load_skill_state(state_dir: Path | None) -> dict[str, dict[str, Any]]:
    """Return persisted per-skill overrides: {id: {enabled?, text?}}."""
    if not state_dir:
        return {}
    path = _state_file(state_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_skill_state(state_dir: Path, state: dict[str, dict[str, Any]]) -> None:
    path = _state_file(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _apply_state(skill: LoadedSkill, entry: dict[str, Any]) -> LoadedSkill:
    if "enabled" in entry:
        # A skill that fails validation can never be enabled (HL-ASSIST-03).
        skill.enabled = bool(entry["enabled"]) and skill.disabled_reason is None
    return skill


def load_skill_registry(
    *,
    builtin_dir: Path | None = None,
    global_dir: Path | None = None,
    project_dir: Path | None = None,
    state_dir: Path | None = None,
) -> SkillRegistry:
    """Load HydraLab-managed skill descriptors from builtin/global/project folders.

    Third-party plugin manifests are rejected (HL-ASSIST-11); only Markdown+YAML
    skill files load. Persisted per-skill ``enabled`` toggles and body edits in
    ``state_dir`` are applied on top so choices survive a project reopen
    (HL-ASSIST-02, HL-ASSIST-05).
    """
    registry = SkillRegistry()
    state = load_skill_state(state_dir)
    scope_dirs: list[tuple[str, Path | None]] = [
        ("builtin", builtin_dir or builtin_skills_dir()),
        ("global", global_dir),
        ("project", project_dir),
    ]
    for scope, directory in scope_dirs:
        if not directory or not Path(directory).exists():
            continue
        for path in sorted(Path(directory).glob("*")):
            if path.name in PLUGIN_MANIFEST_NAMES or path.suffix == ".json":
                registry.rejected_plugins.append({"path": str(path), "reason": PLUGIN_REJECTION_MESSAGE})
                continue
            if path.suffix not in {".md", ".markdown"}:
                continue
            skill = _skill_from_file(path, scope)
            entry = state.get(skill.id)
            if entry and entry.get("text"):
                skill = _skill_from_text(
                    str(entry["text"]), path, scope, fallback_stem=skill.id, edited=True
                )
            if entry:
                skill = _apply_state(skill, entry)
            registry.skills.append(skill)
    return registry


def factory_text(skill_id: str, *, builtin_dir: Path | None = None) -> str | None:
    """Return the on-disk factory text of a built-in skill, if present."""
    directory = builtin_dir or builtin_skills_dir()
    for path in sorted(Path(directory).glob("*")):
        if path.suffix not in {".md", ".markdown"}:
            continue
        front_matter, _ = parse_skill_file(path.read_text(encoding="utf-8"))
        if str(front_matter.get("id") or path.stem) == skill_id:
            return path.read_text(encoding="utf-8")
    return None


def set_skill_enabled(state_dir: Path, skill: LoadedSkill, enabled: bool) -> None:
    """Persist a per-skill enabled toggle. An invalid skill cannot be enabled."""
    if enabled and skill.disabled_reason is not None:
        raise ValueError(f"cannot enable invalid skill: {skill.disabled_reason}")
    state = load_skill_state(state_dir)
    entry = state.setdefault(skill.id, {})
    entry["enabled"] = bool(enabled)
    save_skill_state(state_dir, state)


def edit_skill_text(state_dir: Path, skill_id: str, text: str) -> str | None:
    """Persist an edited skill body/front matter. Returns a validation error or None."""
    front_matter, body = parse_skill_file(text)
    reason = validate_skill(front_matter, body)
    state = load_skill_state(state_dir)
    entry = state.setdefault(skill_id, {})
    entry["text"] = text
    save_skill_state(state_dir, state)
    return reason


def restore_skill(state_dir: Path, skill_id: str) -> None:
    """Drop any user edit so the skill reverts to its factory text (HL-ASSIST-05)."""
    state = load_skill_state(state_dir)
    entry = state.get(skill_id)
    if entry and "text" in entry:
        del entry["text"]
        if not entry:
            del state[skill_id]
        save_skill_state(state_dir, state)
