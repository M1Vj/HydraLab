from pathlib import Path

from hydra.skills.registry import (
    PLUGIN_REJECTION_MESSAGE,
    load_skill_registry,
    parse_skill_file,
    validate_skill,
)

VALID_SKILL = """---
id: {id}
name: {name}
version: "1.0.0"
scope: {scope}
description: A valid skill.
enabled_by_default: {enabled}
allowed_capabilities:
  - read_context
risk_level: low
requires_approval: false
tags:
  - test
---

# Purpose
p
# When To Use
w
# Inputs
i
# Workflow
wf
# Outputs
o
# Safety
s
# References
r
"""

MISSING_SAFETY = """---
id: summarize-source
name: Summarize Source
version: "1.0.0"
scope: project
description: Missing safety section.
enabled_by_default: true
allowed_capabilities: []
risk_level: low
requires_approval: false
tags: []
---

# Purpose
p
# When To Use
w
# Inputs
i
# Workflow
wf
# Outputs
o
# References
r
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# @HL-ASSIST-08 — a valid skill in each scope loads.
def test_hl_assist_08_loads_by_scope(tmp_path):
    global_dir = tmp_path / "global"
    project_dir = tmp_path / "project"
    _write(global_dir / "g.md", VALID_SKILL.format(id="global-skill", name="Global", scope="global", enabled="true"))
    _write(project_dir / "p.md", VALID_SKILL.format(id="project-skill", name="Project", scope="project", enabled="true"))
    registry = load_skill_registry(global_dir=global_dir, project_dir=project_dir)
    scopes = {s.scope for s in registry.skills}
    assert {"builtin", "global", "project"} <= scopes
    assert registry.get("global-skill").enabled is True
    assert registry.get("project-skill").enabled is True


# @HL-ASSIST-09 — a skill missing a required section stays disabled with a reason.
def test_hl_assist_09_missing_section_disabled_with_reason(tmp_path):
    project_dir = tmp_path / "project"
    _write(project_dir / "summarize-source.md", MISSING_SAFETY)
    registry = load_skill_registry(builtin_dir=tmp_path / "none", project_dir=project_dir)
    skill = registry.get("summarize-source")
    assert skill.enabled is False
    assert skill.disabled_reason == "missing required section: # Safety"


# @HL-ASSIST-10 — Settings shows scope, risk_level and requires_approval.
def test_hl_assist_10_scope_risk_visibility(tmp_path):
    project_dir = tmp_path / "project"
    _write(project_dir / "s.md", VALID_SKILL.format(id="summarize-source", name="Summarize Source", scope="project", enabled="true"))
    registry = load_skill_registry(builtin_dir=tmp_path / "none", project_dir=project_dir)
    api = registry.get("summarize-source").to_api()
    assert api["scope"] == "project"
    assert api["risk_level"] == "low"
    assert api["requires_approval"] is False


# @HL-ASSIST-11 — a third-party plugin manifest is rejected.
def test_hl_assist_11_plugin_manifest_rejected(tmp_path):
    project_dir = tmp_path / "project"
    _write(project_dir / "plugin.json", '{"name": "evil-plugin", "capabilities": ["shell"]}')
    registry = load_skill_registry(builtin_dir=tmp_path / "none", project_dir=project_dir)
    assert registry.rejected_plugins
    assert registry.rejected_plugins[0]["reason"] == PLUGIN_REJECTION_MESSAGE
    assert PLUGIN_REJECTION_MESSAGE == "plugins not supported in Phase 1"
    # No capability from the manifest becomes an enabled skill.
    assert all(s.id != "evil-plugin" for s in registry.skills)


def test_builtin_skills_ship_valid():
    registry = load_skill_registry()
    ids = {s.id for s in registry.skills}
    assert "summarize-source" in ids
    assert "draft-outline" in ids
    assert registry.get("summarize-source").enabled is True
    assert registry.get("draft-outline").enabled is False


def test_validate_and_parse_helpers():
    front, body = parse_skill_file(VALID_SKILL.format(id="x", name="X", scope="global", enabled="false"))
    assert front["id"] == "x"
    assert validate_skill(front, body) is None
    bad = dict(front)
    bad.pop("risk_level")
    assert "risk_level" in validate_skill(bad, body)
