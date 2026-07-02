"""Permissive CSL rendering path (HL-CITE-05, HL-LIC-01).

The shipped processor is citeproc-py (SPDX ``BSD-2-Clause-Views``), a pure
permissive/weak-copyleft library. citeproc-js (CPAL-1.0/AGPL-3.0) is NEVER
imported or bundled here; it stays a RED-hazard reference row in ATTRIBUTION.md.
CSL style files are vendored as CC-BY-SA-3.0 *data* (attribution only) under
``data/styles/`` and complemented by the locales citeproc-py ships.

Global default style comes from settings; a per-manuscript override in
``writing/manuscripts/<name>/paper.yaml`` wins when present (Section 15, 26.9).
Hostile HTML/script-like metadata is escaped on render (Guardrails).
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from citeproc import Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle, formatter
from citeproc.source.json import CiteProcJSON

# The permissive processor + shipped default style. APA is chosen as the global
# default (documented in DATABASE-ERD-RLS.md / ATTRIBUTION.md).
CSL_PROCESSOR = "citeproc-py"
DEFAULT_STYLE_ID = "apa"

_STYLES_DIR = Path(__file__).resolve().parent / "data" / "styles"
_STYLE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class CslRenderError(RuntimeError):
    """Raised when a style cannot be loaded or an item cannot be rendered."""


class CslRenderer:
    def __init__(self, styles_dir: Path | None = None, default_style: str = DEFAULT_STYLE_ID) -> None:
        self.styles_dir = styles_dir or _STYLES_DIR
        self.default_style = default_style

    def available_styles(self) -> list[str]:
        if not self.styles_dir.exists():
            return []
        return sorted(path.stem for path in self.styles_dir.glob("*.csl"))

    def resolve_style_path(self, style_id: str | None) -> Path:
        candidate = (style_id or self.default_style).strip().lower()
        if not _STYLE_ID_RE.match(candidate):
            raise CslRenderError(f"Unsafe CSL style id: {style_id!r}")
        vendored = self.styles_dir / f"{candidate}.csl"
        if vendored.exists():
            return vendored
        fallback = self.styles_dir / f"{self.default_style}.csl"
        if fallback.exists():
            return fallback
        raise CslRenderError(f"No CSL style available for {style_id!r}")

    def render_bibliography(self, items: list[dict[str, Any]], style_id: str | None = None) -> list[str]:
        """Render a list of CSL-JSON items to plain-text bibliography entries."""
        if not items:
            return []
        style_path = self.resolve_style_path(style_id)
        prepared = [self._prepare(item, index) for index, item in enumerate(items)]
        source = CiteProcJSON(prepared)
        try:
            style = CitationStylesStyle(str(style_path), locale="en-US", validate=False)
            bibliography = CitationStylesBibliography(style, source, formatter.plain)
            for item in prepared:
                bibliography.register(Citation([CitationItem(item["id"])]))
            rendered = [str(entry) for entry in bibliography.bibliography()]
        except CslRenderError:
            raise
        except Exception as exc:  # citeproc raises assorted parse/render errors
            raise CslRenderError(f"Could not render bibliography: {exc}") from exc
        return rendered

    def render_bibliography_html(self, items: list[dict[str, Any]], style_id: str | None = None) -> list[str]:
        """Render + HTML-escape so hostile metadata cannot inject markup."""
        return [html.escape(entry) for entry in self.render_bibliography(items, style_id)]

    def _prepare(self, item: dict[str, Any], index: int) -> dict[str, Any]:
        prepared = dict(item)
        prepared.setdefault("id", f"item-{index}")
        prepared.setdefault("type", "article-journal")
        return prepared


def resolve_manuscript_style(project_root: Path, manuscript: str | None, global_default: str) -> str:
    """Return the active style id, letting a manuscript's paper.yaml override.

    ``writing/manuscripts/<name>/paper.yaml`` may set ``citation_style`` /
    ``csl_style``; otherwise the global default from settings is used.
    """
    if not manuscript:
        return global_default
    paper_yaml = Path(project_root) / "writing" / "manuscripts" / manuscript / "paper.yaml"
    if not paper_yaml.exists():
        return global_default
    try:
        from ruamel.yaml import YAML

        data = YAML(typ="safe").load(paper_yaml.read_text()) or {}
    except Exception:
        return global_default
    if isinstance(data, dict):
        for key in ("citation_style", "csl_style", "default_citation_style"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
    return global_default
