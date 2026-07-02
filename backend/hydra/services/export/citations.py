"""Permissive, HydraLab-owned citation serializers (HL-EXPORT-01 / DEC-1).

BibTeX, CSL JSON and RIS are produced by hand here. We deliberately do NOT bundle
citeproc-js (CPAL/AGPL); CSL JSON is emitted through this permissive path.
"""
from __future__ import annotations

import json
import re
from typing import Any

CITATION_FORMATS: tuple[str, ...] = ("bibtex", "csl", "ris")


def _authors_list(source: dict[str, Any]) -> list[str]:
    authors = source.get("authors")
    if isinstance(authors, list):
        return [str(a) for a in authors if a]
    if isinstance(authors, str) and authors.strip():
        parts = re.split(r"\s*(?:;| and |,(?=\s*[A-Z][a-z]+\s+[A-Z]))\s*", authors)
        return [p.strip() for p in parts if p.strip()]
    return []


def _year(source: dict[str, Any]) -> str:
    year = source.get("year")
    if year in (None, ""):
        return ""
    return str(year)


def _citation_key(source: dict[str, Any]) -> str:
    authors = _authors_list(source)
    last = ""
    if authors:
        last = authors[0].split()[-1] if authors[0].split() else authors[0]
    last = re.sub(r"[^A-Za-z0-9]", "", last) or "source"
    year = _year(source) or "nd"
    key = source.get("citation_key") or f"{last}{year}"
    return re.sub(r"[^A-Za-z0-9]", "", str(key)) or "source"


def to_bibtex(sources: list[dict[str, Any]]) -> str:
    entries: list[str] = []
    for source in sources:
        fields = [("title", source.get("title") or "Untitled")]
        authors = _authors_list(source)
        if authors:
            fields.append(("author", " and ".join(authors)))
        if _year(source):
            fields.append(("year", _year(source)))
        if source.get("doi"):
            fields.append(("doi", str(source["doi"])))
        if source.get("url"):
            fields.append(("url", str(source["url"])))
        body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields)
        entries.append(f"@article{{{_citation_key(source)},\n{body}\n}}")
    return "\n\n".join(entries)


def to_csl_json(sources: list[dict[str, Any]]) -> str:
    items: list[dict[str, Any]] = []
    for source in sources:
        item: dict[str, Any] = {
            "id": _citation_key(source),
            "type": "article-journal",
            "title": source.get("title") or "Untitled",
        }
        authors = _authors_list(source)
        if authors:
            item["author"] = [_csl_name(name) for name in authors]
        if _year(source):
            digits = re.findall(r"\d{4}", _year(source))
            if digits:
                item["issued"] = {"date-parts": [[int(digits[0])]]}
        if source.get("doi"):
            item["DOI"] = str(source["doi"])
        if source.get("url"):
            item["URL"] = str(source["url"])
        items.append(item)
    return json.dumps(items, indent=2)


def _csl_name(name: str) -> dict[str, str]:
    parts = name.split()
    if len(parts) == 1:
        return {"family": parts[0]}
    return {"family": parts[-1], "given": " ".join(parts[:-1])}


def to_ris(sources: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for source in sources:
        lines = ["TY  - JOUR", f"TI  - {source.get('title') or 'Untitled'}"]
        for author in _authors_list(source):
            lines.append(f"AU  - {author}")
        if _year(source):
            lines.append(f"PY  - {_year(source)}")
        if source.get("doi"):
            lines.append(f"DO  - {source['doi']}")
        if source.get("url"):
            lines.append(f"UR  - {source['url']}")
        lines.append("ER  - ")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
