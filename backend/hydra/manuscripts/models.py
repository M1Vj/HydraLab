"""Shared manuscript document model used by every export target."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hydra.services.writing import ManuscriptFormat


@dataclass(frozen=True)
class ManuscriptSection:
    title: str
    content: str
    authorship: str = "human"


@dataclass(frozen=True)
class ManuscriptFigure:
    id: str
    path: str
    caption: str
    number: int

    @property
    def label(self) -> str:
        return f"Figure {self.number}"


@dataclass(frozen=True)
class ManuscriptTable:
    id: str
    caption: str
    markdown: str
    number: int

    @property
    def label(self) -> str:
        return f"Table {self.number}"


@dataclass(frozen=True)
class CitationValidation:
    unresolved_citation_keys: list[str] = field(default_factory=list)
    missing_metadata: list[dict[str, str]] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.unresolved_citation_keys or self.missing_metadata)

    def public_dict(self) -> dict[str, Any]:
        return {
            "unresolved_citation_keys": list(self.unresolved_citation_keys),
            "missing_metadata": list(self.missing_metadata),
            "has_issues": self.has_issues,
        }


@dataclass(frozen=True)
class RedactionItem:
    id: str
    category: str
    path: str
    reason: str
    decision: str = "remove-or-acknowledge"

    def public_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "category": self.category,
            "path": self.path,
            "reason": self.reason,
            "decision": self.decision,
        }


@dataclass(frozen=True)
class RedactionReport:
    items: list[RedactionItem] = field(default_factory=list)

    @property
    def has_unresolved(self) -> bool:
        return bool(self.items)

    def unresolved(self, acknowledged_ids: set[str]) -> list[RedactionItem]:
        return [item for item in self.items if item.id not in acknowledged_ids]

    def public_dict(self) -> dict[str, Any]:
        return {"items": [item.public_dict() for item in self.items], "has_unresolved": self.has_unresolved}


@dataclass(frozen=True)
class ManuscriptDocument:
    manuscript_id: str
    source_dir: str
    format: ManuscriptFormat
    template_id: str
    sections: list[ManuscriptSection]
    figures: list[ManuscriptFigure]
    tables: list[ManuscriptTable]
    citation_keys: list[str]
    references: dict[str, dict[str, Any]]
    source_files: list[str]
    include_paths: list[str] = field(default_factory=list)

    @property
    def authorship_ledger(self) -> list[dict[str, str]]:
        return [{"section": section.title, "authorship": section.authorship} for section in self.sections]

    def public_dict(self) -> dict[str, Any]:
        return {
            "manuscript_id": self.manuscript_id,
            "source_dir": self.source_dir,
            "format": self.format.model_dump(),
            "template_id": self.template_id,
            "sections": [section.__dict__ for section in self.sections],
            "figures": [figure.__dict__ | {"label": figure.label} for figure in self.figures],
            "tables": [table.__dict__ | {"label": table.label} for table in self.tables],
            "citation_keys": list(self.citation_keys),
            "references": self.references,
            "source_files": list(self.source_files),
            "include_paths": list(self.include_paths),
            "authorship_ledger": self.authorship_ledger,
        }
