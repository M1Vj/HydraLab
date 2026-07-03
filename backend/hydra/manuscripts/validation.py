"""Citation and source-metadata validation for manuscript packages."""

from __future__ import annotations

from .models import CitationValidation, ManuscriptDocument

REQUIRED_REFERENCE_FIELDS = ("title", "authors", "year")


def validate_citations(document: ManuscriptDocument) -> CitationValidation:
    unresolved = [key for key in document.citation_keys if key not in document.references]
    missing: list[dict[str, str]] = []
    for key in document.citation_keys:
        source = document.references.get(key)
        if not source:
            continue
        fields = [field for field in REQUIRED_REFERENCE_FIELDS if not str(source.get(field) or "").strip()]
        if fields:
            missing.append({"citation_key": key, "missing_fields": ", ".join(fields)})
    return CitationValidation(unresolved_citation_keys=unresolved, missing_metadata=missing)
