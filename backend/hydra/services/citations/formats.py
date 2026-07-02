"""HydraLab-owned citation format conversion.

CSL JSON is the canonical interchange (Section 26.9). BibTeX/RIS are
import/export-only derived formats. This module wraps permissive parsers
(bibtexparser==1.4.4 BSD, rispy MIT) behind a HydraLab contract so no third
party structure is ever the source of truth. Malformed input is contained and
surfaced as a typed :class:`CitationParseError`; it never mutates or deletes
existing records (HL-CITE-01, HL-CITE-13).
"""
from __future__ import annotations

import re
from typing import Any

import bibtexparser
import rispy
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.customization import author as split_author
from bibtexparser.customization import convert_to_unicode


class CitationParseError(ValueError):
    """Raised when a BibTeX/RIS/CSL-JSON payload cannot be parsed.

    Carries the offending entry key (when known) so the importer can show an
    actionable error without touching any existing record.
    """

    def __init__(self, message: str, *, entry: str | None = None) -> None:
        super().__init__(message)
        self.entry = entry


# --- CSL <-> BibTeX type maps -------------------------------------------------

_BIBTEX_TO_CSL_TYPE = {
    "article": "article-journal",
    "book": "book",
    "booklet": "book",
    "inbook": "chapter",
    "incollection": "chapter",
    "inproceedings": "paper-conference",
    "conference": "paper-conference",
    "manual": "book",
    "mastersthesis": "thesis",
    "phdthesis": "thesis",
    "misc": "article",
    "proceedings": "book",
    "techreport": "report",
    "unpublished": "manuscript",
}
_CSL_TO_BIBTEX_TYPE = {
    "article-journal": "article",
    "article": "article",
    "book": "book",
    "chapter": "incollection",
    "paper-conference": "inproceedings",
    "thesis": "phdthesis",
    "report": "techreport",
    "manuscript": "unpublished",
}

# --- CSL <-> RIS type maps ----------------------------------------------------

_RIS_TO_CSL_TYPE = {
    "JOUR": "article-journal",
    "BOOK": "book",
    "CHAP": "chapter",
    "CONF": "paper-conference",
    "CPAPER": "paper-conference",
    "RPRT": "report",
    "THES": "thesis",
    "GEN": "article",
    "ELEC": "webpage",
}
_CSL_TO_RIS_TYPE = {
    "article-journal": "JOUR",
    "article": "JOUR",
    "book": "BOOK",
    "chapter": "CHAP",
    "paper-conference": "CONF",
    "report": "RPRT",
    "thesis": "THES",
    "webpage": "ELEC",
}

_STOP_WORDS = {"a", "an", "the", "on", "of", "in", "for", "and", "to", "is", "at"}
_ENTRY_START = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE)


def _clean_authors_to_csl(author_field: str) -> list[dict[str, str]]:
    parts = [a.strip() for a in re.split(r"\s+and\s+", author_field) if a.strip()]
    people: list[dict[str, str]] = []
    for part in parts:
        if "," in part:
            family, _, given = part.partition(",")
            people.append({"family": family.strip(), "given": given.strip()})
        else:
            tokens = part.split()
            if len(tokens) > 1:
                people.append({"family": tokens[-1], "given": " ".join(tokens[:-1])})
            else:
                people.append({"family": part})
    return people


def _csl_authors_to_string(authors: Any) -> str:
    names: list[str] = []
    for person in authors or []:
        if isinstance(person, dict):
            family = person.get("family", "").strip()
            given = person.get("given", "").strip()
            names.append(f"{family}, {given}".strip(", ") if family or given else "")
        else:
            names.append(str(person))
    return " and ".join(name for name in names if name)


def _year_from_csl(item: dict[str, Any]) -> str:
    issued = item.get("issued") or {}
    parts = issued.get("date-parts") if isinstance(issued, dict) else None
    if parts and parts[0]:
        return str(parts[0][0])
    return ""


def _issued_from_year(year: Any) -> dict[str, Any] | None:
    if year in (None, ""):
        return None
    match = re.search(r"\d{4}", str(year))
    if not match:
        return None
    return {"date-parts": [[int(match.group(0))]]}


# --- BibTeX -------------------------------------------------------------------

def bibtex_to_csl_json(text: str) -> list[dict[str, Any]]:
    """Parse BibTeX into a list of CSL-JSON items.

    Malformed input (e.g. an unterminated entry) raises
    :class:`CitationParseError` naming the failing entry key; no partial import
    is returned so callers never silently drop data.
    """
    if not text or not text.strip():
        return []

    declared = _ENTRY_START.findall(text)
    declared_keys = [key for kind, key in declared if kind.lower() not in {"comment", "string", "preamble"}]

    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    parser.customization = lambda record: convert_to_unicode(split_author(record))
    try:
        database = bibtexparser.loads(text, parser=parser)
    except Exception as exc:  # bibtexparser raises assorted exceptions
        raise CitationParseError(f"Could not parse BibTeX: {exc}") from exc

    parsed_keys = [entry.get("ID", "") for entry in database.entries]
    if declared_keys and len(parsed_keys) < len(declared_keys):
        missing = next((key for key in declared_keys if key not in parsed_keys), declared_keys[-1])
        raise CitationParseError(
            f"BibTeX entry '{missing}' is malformed or unterminated.",
            entry=missing,
        )

    items: list[dict[str, Any]] = []
    for entry in database.entries:
        items.append(_bibtex_entry_to_csl(entry))
    return items


def _bibtex_entry_to_csl(entry: dict[str, Any]) -> dict[str, Any]:
    csl: dict[str, Any] = {
        "id": entry.get("ID") or "",
        "type": _BIBTEX_TO_CSL_TYPE.get(str(entry.get("ENTRYTYPE", "")).lower(), "article"),
    }
    if entry.get("title"):
        csl["title"] = _strip_braces(entry["title"])
    author = entry.get("author")
    if author:
        if isinstance(author, list):
            csl["author"] = _clean_authors_to_csl(" and ".join(author))
        else:
            csl["author"] = _clean_authors_to_csl(author)
    issued = _issued_from_year(entry.get("year"))
    if issued:
        csl["issued"] = issued
    for src, dst in (
        ("journal", "container-title"),
        ("booktitle", "container-title"),
        ("publisher", "publisher"),
        ("doi", "DOI"),
        ("url", "URL"),
        ("volume", "volume"),
        ("number", "issue"),
        ("pages", "page"),
        ("abstract", "abstract"),
    ):
        value = entry.get(src)
        if value:
            csl[dst] = _strip_braces(value) if isinstance(value, str) else value
    if entry.get("keywords"):
        csl["keyword"] = _strip_braces(entry["keywords"])
    return csl


def csl_json_to_bibtex(items: list[dict[str, Any]]) -> str:
    database = bibtexparser.bibdatabase.BibDatabase()
    entries = []
    for index, item in enumerate(items):
        entry_type = _CSL_TO_BIBTEX_TYPE.get(str(item.get("type", "")), "article")
        entry: dict[str, Any] = {
            "ENTRYTYPE": entry_type,
            "ID": item.get("id") or citation_key(item) or f"entry{index + 1}",
        }
        if item.get("title"):
            entry["title"] = str(item["title"])
        if item.get("author"):
            entry["author"] = _csl_authors_to_string(item["author"])
        year = _year_from_csl(item)
        if year:
            entry["year"] = year
        for src, dst in (
            ("container-title", "journal"),
            ("publisher", "publisher"),
            ("DOI", "doi"),
            ("URL", "url"),
            ("volume", "volume"),
            ("issue", "number"),
            ("page", "pages"),
            ("abstract", "abstract"),
        ):
            if item.get(src):
                entry[dst] = str(item[src])
        entries.append(entry)
    database.entries = entries
    writer = BibTexWriter()
    writer.order_entries_by = None
    return writer.write(database).strip()


# --- RIS ----------------------------------------------------------------------

def ris_to_csl_json(text: str) -> list[dict[str, Any]]:
    if not text or not text.strip():
        return []
    try:
        entries = rispy.loads(text)
    except Exception as exc:
        raise CitationParseError(f"Could not parse RIS: {exc}") from exc
    if not entries and text.strip():
        raise CitationParseError("RIS payload contained no recognizable entries.")
    return [_ris_entry_to_csl(entry) for entry in entries]


def _ris_entry_to_csl(entry: dict[str, Any]) -> dict[str, Any]:
    csl: dict[str, Any] = {
        "id": entry.get("id") or entry.get("doi") or "",
        "type": _RIS_TO_CSL_TYPE.get(str(entry.get("type_of_reference", "GEN")).upper(), "article"),
    }
    if entry.get("title") or entry.get("primary_title"):
        csl["title"] = entry.get("title") or entry.get("primary_title")
    authors = entry.get("authors") or entry.get("first_authors") or []
    if authors:
        csl["author"] = _clean_authors_to_csl(" and ".join(authors))
    year = entry.get("year") or entry.get("publication_year")
    issued = _issued_from_year(year)
    if issued:
        csl["issued"] = issued
    for src, dst in (
        ("journal_name", "container-title"),
        ("secondary_title", "container-title"),
        ("publisher", "publisher"),
        ("doi", "DOI"),
        ("url", "URL"),
        ("volume", "volume"),
        ("number", "issue"),
        ("abstract", "abstract"),
    ):
        if entry.get(src):
            csl[dst] = entry[src]
    return csl


def csl_json_to_ris(items: list[dict[str, Any]]) -> str:
    entries = []
    for item in items:
        entry: dict[str, Any] = {
            "type_of_reference": _CSL_TO_RIS_TYPE.get(str(item.get("type", "")), "JOUR"),
        }
        if item.get("id"):
            entry["id"] = str(item["id"])
        if item.get("title"):
            entry["title"] = str(item["title"])
        authors = [name for name in _csl_authors_to_string(item.get("author")).split(" and ") if name]
        if authors:
            entry["authors"] = authors
        year = _year_from_csl(item)
        if year:
            entry["year"] = year
        for src, dst in (
            ("container-title", "journal_name"),
            ("publisher", "publisher"),
            ("DOI", "doi"),
            ("URL", "url"),
            ("volume", "volume"),
            ("issue", "number"),
            ("abstract", "abstract"),
        ):
            if item.get(src):
                entry[dst] = str(item[src])
        entries.append(entry)
    return rispy.dumps(entries)


# --- Citation key -------------------------------------------------------------

def citation_key(item: dict[str, Any]) -> str:
    """Deterministic citation key: ``<firstauthorfamily><year><firsttitleword>``.

    Same input always yields the same key (HL-CITE-03). Falls back to ``id`` or
    ``anon`` when authorship is missing.
    """
    authors = item.get("author") or []
    family = ""
    if authors:
        first = authors[0]
        family = first.get("family", "") if isinstance(first, dict) else str(first)
    family = re.sub(r"[^a-z0-9]", "", family.lower()) or ""
    year = _year_from_csl(item) or ""
    title = str(item.get("title") or "")
    first_word = ""
    for token in re.split(r"\s+", title):
        cleaned = re.sub(r"[^a-z0-9]", "", token.lower())
        if cleaned and cleaned not in _STOP_WORDS:
            first_word = cleaned
            break
    key = f"{family}{year}{first_word}"
    if not key:
        return re.sub(r"[^a-z0-9]", "", str(item.get("id") or "anon").lower()) or "anon"
    return key


def _strip_braces(value: str) -> str:
    return value.replace("{", "").replace("}", "").strip()
