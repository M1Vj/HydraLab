"""Manuscript format model, ``paper.yaml`` parser, and effective-format merge.

HydraLab formatting is more than citation style (Section 15, HL-WRITE-18): the
typed :class:`ManuscriptFormat` covers the full final-output appearance (font,
spacing, margins, page size, orientation, headings, captions, columns,
headers/footers, references) and citation style is one field among these.

Two-layer resolution (HL-WRITE-16/17): global defaults live in ``settings.toml``
``[writing]``; a per-manuscript ``writing/manuscripts/<name>/paper.yaml`` may
override them field-by-field with the manuscript winning. A malformed
``paper.yaml`` never crashes the writing module — it surfaces a typed
validation-failure state naming the offending key and falls back to the global
defaults (HL-WRITE-15).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# Allowed enumerations for validated fields. Values are lower-cased before check.
PAGE_SIZES = {"a4", "a5", "b5", "letter", "legal"}
ORIENTATIONS = {"portrait", "landscape"}
CAPTION_POSITIONS = {"above", "below"}
REFERENCE_FORMATS = {"hanging", "numbered", "plain"}

# Regexes for dimension-like fields.
_LENGTH_RE = r"^\d+(\.\d+)?(pt|px|in|cm|mm|em)$"


class FormatValidationError(ValueError):
    """Raised when a ``paper.yaml`` value is invalid.

    ``key`` names the offending field so the UI can point at it and fall back to
    the global default rather than crashing (HL-WRITE-15).
    """

    def __init__(self, key: str, message: str) -> None:
        super().__init__(message)
        self.key = key


class ManuscriptFormat(BaseModel):
    """Typed manuscript-format model covering full output appearance."""

    citation_style: str = "apa"
    font_family: str = "Times New Roman"
    font_size: str = "12pt"
    line_spacing: float = 1.0
    paragraph_spacing: str = "0pt"
    margins: str = "1in"
    page_size: str = "letter"
    orientation: str = "portrait"
    heading_numbering: bool = False
    title_page: bool = True
    abstract: bool = True
    columns: int = 1
    figure_caption: str = "below"
    table_caption: str = "above"
    reference_format: str = "hanging"
    page_numbers: bool = True
    headers_footers: bool = False
    manuscript_template: str = "generic-academic"
    docx_template: str = "generic-academic"


# The default format when neither settings nor paper.yaml specify a field.
DEFAULT_FORMAT_FIELDS: dict[str, Any] = ManuscriptFormat().model_dump()

# Keys accepted from ``settings.toml`` ``[writing]`` and mapped onto the format.
_SETTINGS_KEY_ALIASES = {
    "default_citation_style": "citation_style",
    "citation_style": "citation_style",
    "manuscript_template": "manuscript_template",
    "manuscript_format": "manuscript_template",
    "docx_template": "docx_template",
    "docx_style": "docx_template",
}

# Aliases accepted inside ``paper.yaml`` for the citation-style key (branch 01-09
# already reads these in ``resolve_manuscript_style``; keep them consistent).
_PAPER_KEY_ALIASES = {
    "csl_style": "citation_style",
    "default_citation_style": "citation_style",
}


@dataclass
class ResolvedFormat:
    """Effective format plus an optional validation-failure state."""

    format: ManuscriptFormat
    validation_error: dict[str, str] | None = None
    source: str = "global"  # "global" | "merged"


def _coerce_field(key: str, value: Any) -> Any:
    """Validate + normalize a single override value, raising with the key."""
    if key == "page_size":
        text = str(value).strip().lower()
        if text not in PAGE_SIZES:
            raise FormatValidationError(key, f"invalid page_size {value!r}; expected one of {sorted(PAGE_SIZES)}")
        return text
    if key == "orientation":
        text = str(value).strip().lower()
        if text not in ORIENTATIONS:
            raise FormatValidationError(key, f"invalid orientation {value!r}")
        return text
    if key in {"figure_caption", "table_caption"}:
        text = str(value).strip().lower()
        if text not in CAPTION_POSITIONS:
            raise FormatValidationError(key, f"invalid {key} {value!r}; expected above/below")
        return text
    if key == "reference_format":
        text = str(value).strip().lower()
        if text not in REFERENCE_FORMATS:
            raise FormatValidationError(key, f"invalid reference_format {value!r}")
        return text
    if key in {"font_size", "margins", "paragraph_spacing"}:
        import re

        text = str(value).strip()
        if not re.match(_LENGTH_RE, text):
            raise FormatValidationError(key, f"invalid {key} {value!r}; expected a length like '11pt' or '1in'")
        return text
    if key == "line_spacing":
        try:
            spacing = float(value)
        except (TypeError, ValueError) as exc:
            raise FormatValidationError(key, f"invalid line_spacing {value!r}") from exc
        if spacing <= 0 or spacing > 5:
            raise FormatValidationError(key, f"line_spacing {value!r} out of range (0, 5]")
        return spacing
    if key == "columns":
        try:
            columns = int(value)
        except (TypeError, ValueError) as exc:
            raise FormatValidationError(key, f"invalid columns {value!r}") from exc
        if columns not in {1, 2}:
            raise FormatValidationError(key, f"columns {value!r} must be 1 or 2")
        return columns
    if key in {"heading_numbering", "title_page", "abstract", "page_numbers", "headers_footers"}:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "on", "yes", "1"}:
            return True
        if text in {"false", "off", "no", "0"}:
            return False
        raise FormatValidationError(key, f"invalid boolean {value!r} for {key}")
    if key in {"citation_style", "font_family", "manuscript_template", "docx_template"}:
        return str(value).strip()
    # Unknown keys are ignored (round-trip friendly), not fatal.
    return None


def normalize_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate + normalize a raw override dict into known format fields.

    Raises :class:`FormatValidationError` on the first invalid known key.
    """
    normalized: dict[str, Any] = {}
    for raw_key, value in raw.items():
        key = _PAPER_KEY_ALIASES.get(raw_key, raw_key)
        if key not in DEFAULT_FORMAT_FIELDS:
            continue  # unknown key: preserved by the file, ignored by the model
        coerced = _coerce_field(key, value)
        if coerced is not None:
            normalized[key] = coerced
    return normalized


def global_defaults_from_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    """Map ``settings.toml`` ``[writing]`` (+ ``[citations]``) onto format fields."""
    fields = dict(DEFAULT_FORMAT_FIELDS)
    if not isinstance(settings, dict):
        return fields
    writing = settings.get("writing", {}) if isinstance(settings.get("writing"), dict) else {}
    citations = settings.get("citations", {}) if isinstance(settings.get("citations"), dict) else {}
    for section in (citations, writing):  # writing wins over citations
        for raw_key, value in section.items():
            mapped = _SETTINGS_KEY_ALIASES.get(raw_key)
            if mapped and isinstance(value, (str, int, float, bool)):
                fields[mapped] = str(value).strip() if mapped != "citation_style" else str(value).strip().lower()
    return fields


def merge_format(global_defaults: dict[str, Any], manuscript_overrides: dict[str, Any]) -> ManuscriptFormat:
    """Per-field merge, manuscript overrides winning (HL-WRITE-17)."""
    merged = dict(DEFAULT_FORMAT_FIELDS)
    merged.update({k: v for k, v in global_defaults.items() if k in DEFAULT_FORMAT_FIELDS})
    merged.update({k: v for k, v in manuscript_overrides.items() if k in DEFAULT_FORMAT_FIELDS})
    return ManuscriptFormat(**merged)


def parse_paper_yaml(text: str) -> dict[str, Any]:
    """Load a ``paper.yaml`` string into a raw dict (safe loader, no exec)."""
    from ruamel.yaml import YAML

    data = YAML(typ="safe").load(text) or {}
    if not isinstance(data, dict):
        raise FormatValidationError("paper.yaml", "paper.yaml must be a mapping")
    return data


def manuscript_paper_yaml_path(project_root: Path, manuscript: str) -> Path:
    return Path(project_root) / "writing" / "manuscripts" / manuscript / "paper.yaml"


def resolve_manuscript_format(
    project_root: Path,
    manuscript: str | None,
    global_defaults: dict[str, Any],
) -> ResolvedFormat:
    """Resolve the effective format, degrading gracefully on a bad paper.yaml.

    A missing ``paper.yaml`` returns the global defaults. A malformed one returns
    the global defaults plus a ``validation_error`` naming the offending key —
    the writing module stays usable (HL-WRITE-15).
    """
    base = merge_format(global_defaults, {})
    if not manuscript:
        return ResolvedFormat(format=base, source="global")

    paper_path = manuscript_paper_yaml_path(project_root, manuscript)
    if not paper_path.exists():
        return ResolvedFormat(format=base, source="global")

    try:
        raw = parse_paper_yaml(paper_path.read_text(encoding="utf-8"))
        overrides = normalize_overrides(raw)
    except FormatValidationError as exc:
        return ResolvedFormat(
            format=base,
            validation_error={"key": exc.key, "message": str(exc)},
            source="global",
        )
    except Exception as exc:  # malformed YAML syntax etc.
        return ResolvedFormat(
            format=base,
            validation_error={"key": "paper.yaml", "message": f"could not parse paper.yaml: {exc}"},
            source="global",
        )

    return ResolvedFormat(format=merge_format(global_defaults, overrides), source="merged")


def list_manuscripts(project_root: Path) -> list[str]:
    """List manuscript names under ``writing/manuscripts/``."""
    base = Path(project_root) / "writing" / "manuscripts"
    if not base.exists():
        return []
    return sorted(child.name for child in base.iterdir() if child.is_dir())
