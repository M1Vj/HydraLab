"""HydraLab writing/manuscript-format services (branch 01-12).

Manuscript-format model + ``paper.yaml`` parser + effective-format merge. The
citation-style key is consumed from branch 01-09; CSL rendering itself is NOT
re-implemented here.
"""
from hydra.services.writing.format import (
    DEFAULT_FORMAT_FIELDS,
    FormatValidationError,
    ManuscriptFormat,
    ResolvedFormat,
    global_defaults_from_settings,
    list_manuscripts,
    manuscript_paper_yaml_path,
    merge_format,
    normalize_overrides,
    parse_paper_yaml,
    resolve_manuscript_format,
)

__all__ = [
    "DEFAULT_FORMAT_FIELDS",
    "FormatValidationError",
    "ManuscriptFormat",
    "ResolvedFormat",
    "global_defaults_from_settings",
    "list_manuscripts",
    "manuscript_paper_yaml_path",
    "merge_format",
    "normalize_overrides",
    "parse_paper_yaml",
    "resolve_manuscript_format",
]
