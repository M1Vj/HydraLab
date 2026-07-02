"""HydraLab citation/claim/evidence services (branch 01-09).

Permissive, AGPL-free citation stack: format conversion (bibtexparser/rispy),
CSL rendering (citeproc-py), and confidence-based duplicate detection. All
citeproc-js / Zotero-translator code is excluded by design (DEC-1, HL-LIC-01).
"""
from hydra.services.citations.duplicates import (
    DuplicateVerdict,
    classify_pair,
    find_duplicates,
)
from hydra.services.citations.formats import (
    CitationParseError,
    bibtex_to_csl_json,
    citation_key,
    csl_json_to_bibtex,
    csl_json_to_ris,
    ris_to_csl_json,
)
from hydra.services.citations.render import (
    CSL_PROCESSOR,
    DEFAULT_STYLE_ID,
    CslRenderer,
    CslRenderError,
    resolve_manuscript_style,
)

__all__ = [
    "CitationParseError",
    "bibtex_to_csl_json",
    "csl_json_to_bibtex",
    "ris_to_csl_json",
    "csl_json_to_ris",
    "citation_key",
    "CslRenderer",
    "CslRenderError",
    "CSL_PROCESSOR",
    "DEFAULT_STYLE_ID",
    "resolve_manuscript_style",
    "DuplicateVerdict",
    "classify_pair",
    "find_duplicates",
]
