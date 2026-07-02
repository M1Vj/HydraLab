"""Build a logical manuscript model from working sources."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from hydra.services.writing import global_defaults_from_settings, parse_paper_yaml, resolve_manuscript_format
from hydra.settings.toml_config import default_settings

from .models import ManuscriptDocument, ManuscriptFigure, ManuscriptSection, ManuscriptTable
from .templates import TemplateRegistry, default_template_registry

_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_FIGURE_RE = re.compile(r"!\[(?P<caption>[^\]]+)\]\((?P<path>[^)]+)\)\{#(?P<id>fig:[A-Za-z0-9_.:-]+)\}")
_TABLE_CAPTION_RE = re.compile(r"^Table:\s*(?P<caption>.+?)\s*\{#(?P<id>tbl:[A-Za-z0-9_.:-]+)\}\s*$", re.MULTILINE)
_CITE_RE = re.compile(r"\[@(?P<keys>[^\]]+)\]")


class ManuscriptBuildError(ValueError):
    """Raised when a manuscript source folder cannot be assembled."""


class ManuscriptBuilder:
    def __init__(self, project_root: Path, *, registry: TemplateRegistry | None = None) -> None:
        self.project_root = Path(project_root)
        self.registry = registry or default_template_registry()

    def build(self, manuscript: str) -> ManuscriptDocument:
        manuscript = _safe_name(manuscript)
        source_dir = self.project_root / "writing" / "manuscripts" / manuscript
        if not source_dir.is_dir():
            raise ManuscriptBuildError(f"manuscript source not found: {manuscript}")

        raw_paper = self._paper_yaml(source_dir)
        resolved = resolve_manuscript_format(
            self.project_root,
            manuscript,
            global_defaults_from_settings(default_settings()),
        )
        template = self.registry.get(str(raw_paper.get("manuscript_template") or resolved.format.manuscript_template))
        body_files = self._body_files(source_dir)
        body = "\n\n".join(path.read_text(encoding="utf-8") for path in body_files)
        sections = self._sections(body, self._authorship(source_dir))
        figures = self._figures(body)
        tables = self._tables(body)
        citation_keys = self._citation_keys(body)
        references = self._references(source_dir)
        source_files = [str(path.relative_to(source_dir)) for path in [*body_files, *(source_dir.glob("references.*"))]]
        if (source_dir / "paper.yaml").exists():
            source_files.append("paper.yaml")
        if (source_dir / "authorship.yaml").exists():
            source_files.append("authorship.yaml")

        return ManuscriptDocument(
            manuscript_id=manuscript,
            source_dir=str(source_dir),
            format=resolved.format,
            template_id=template.id,
            sections=sections,
            figures=figures,
            tables=tables,
            citation_keys=citation_keys,
            references=references,
            source_files=sorted(set(source_files)),
            include_paths=[str(item) for item in raw_paper.get("include_paths") or []],
        )

    def _paper_yaml(self, source_dir: Path) -> dict[str, Any]:
        path = source_dir / "paper.yaml"
        if not path.exists():
            return {}
        try:
            return parse_paper_yaml(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _body_files(self, source_dir: Path) -> list[Path]:
        preferred = [source_dir / "main.md", source_dir / "body.md", source_dir / "manuscript.md"]
        existing = [path for path in preferred if path.exists()]
        if existing:
            return existing
        files = [
            path
            for path in sorted(source_dir.glob("*.md"))
            if path.name.lower() not in {"readme.md"} and not path.name.startswith(".")
        ]
        if not files:
            raise ManuscriptBuildError("manuscript must contain main.md, body.md, manuscript.md, or section markdown files")
        return files

    def _sections(self, body: str, authorship: dict[str, str]) -> list[ManuscriptSection]:
        matches = list(_HEADING_RE.finditer(body))
        if not matches:
            return [ManuscriptSection(title="Manuscript", content=body.strip(), authorship=authorship.get("Manuscript", "human"))]
        sections: list[ManuscriptSection] = []
        for index, match in enumerate(matches):
            title = match.group(1).strip()
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            sections.append(
                ManuscriptSection(
                    title=title,
                    content=body[start:end].strip(),
                    authorship=authorship.get(title, "human"),
                )
            )
        return sections

    def _authorship(self, source_dir: Path) -> dict[str, str]:
        path = source_dir / "authorship.yaml"
        if not path.exists():
            return {}
        data = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return {}
        return {
            str(key): "assistant" if str(value).strip().lower() == "assistant" else "human"
            for key, value in data.items()
        }

    def _figures(self, body: str) -> list[ManuscriptFigure]:
        figures: list[ManuscriptFigure] = []
        for match in _FIGURE_RE.finditer(body):
            figures.append(
                ManuscriptFigure(
                    id=match.group("id"),
                    path=match.group("path"),
                    caption=match.group("caption").strip(),
                    number=len(figures) + 1,
                )
            )
        return figures

    def _tables(self, body: str) -> list[ManuscriptTable]:
        tables: list[ManuscriptTable] = []
        lines = body.splitlines()
        for index, line in enumerate(lines):
            match = _TABLE_CAPTION_RE.match(line)
            if not match:
                continue
            table_lines: list[str] = []
            cursor = index + 1
            while cursor < len(lines) and lines[cursor].strip().startswith("|"):
                table_lines.append(lines[cursor])
                cursor += 1
            tables.append(
                ManuscriptTable(
                    id=match.group("id"),
                    caption=match.group("caption").strip(),
                    markdown="\n".join(table_lines),
                    number=len(tables) + 1,
                )
            )
        return tables

    def _citation_keys(self, body: str) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for match in _CITE_RE.finditer(body):
            for raw in re.split(r"[;,]\s*", match.group("keys")):
                key = raw.strip().lstrip("@")
                if key and key not in seen:
                    seen.add(key)
                    ordered.append(key)
        return ordered

    def _references(self, source_dir: Path) -> dict[str, dict[str, Any]]:
        for name in ("references.json", "refs.json", "sources.json"):
            path = source_dir / name
            if path.exists():
                return _references_from_json(path)
        for name in ("references.yaml", "references.yml", "refs.yaml", "refs.yml"):
            path = source_dir / name
            if path.exists():
                return _references_from_yaml(path)
        return {}


def _references_from_json(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return _references_from_data(data)


def _references_from_yaml(path: Path) -> dict[str, dict[str, Any]]:
    data = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    return _references_from_data(data)


def _references_from_data(data: Any) -> dict[str, dict[str, Any]]:
    rows = data.values() if isinstance(data, dict) else data
    references: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list) and not hasattr(rows, "__iter__"):
        return references
    for item in rows:
        if not isinstance(item, dict):
            continue
        key = str(item.get("citation_key") or item.get("key") or item.get("id") or "").strip()
        if not key:
            continue
        references[key] = dict(item, id=key)
    return references


def _safe_name(value: str) -> str:
    if ".." in value or "/" in value or "\\" in value or "\x00" in value or not value.strip():
        raise ManuscriptBuildError("unsafe manuscript name")
    return value.strip()
