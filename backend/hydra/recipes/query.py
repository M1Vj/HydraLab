"""Small, literal query filters for offline saved-source retrieval.

This is not SQL, FTS5 syntax or a regular-expression interface. Plain queries
keep the existing loose-term ranking; quoted phrases are required, and a leading
minus excludes a literal word/phrase. Parsed patterns are compiled once per query.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_QUERY_LENGTH = 2048
MAX_QUERY_CLAUSES = 64


class QuerySyntaxError(ValueError):
    """A local query cannot be interpreted without broadening its scope."""


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text.casefold())


def _word_character(character: str) -> bool:
    return character.isalnum() or character == "_" or unicodedata.category(character).startswith("M")


@dataclass(frozen=True)
class LiteralClause:
    pattern: re.Pattern[str]
    left_boundary: bool
    right_boundary: bool

    def matches(self, text: str) -> bool:
        # Python's \w excludes combining marks. Check Unicode-aware boundaries
        # explicitly so an accent cannot turn a prefix into an exact word hit.
        cursor = 0
        while match := self.pattern.search(text, cursor):
            left_ok = not (self.left_boundary and match.start() and _word_character(text[match.start() - 1]))
            right_ok = not (self.right_boundary and match.end() < len(text) and _word_character(text[match.end()]))
            if left_ok and right_ok:
                return True
            # A rejected prefix can overlap a valid later occurrence ("a a" in
            # "ba a a"). Do not skip straight to this rejected match's end.
            cursor = match.start() + 1
        return False


@dataclass(frozen=True)
class LocalQuery:
    terms: tuple[str, ...]
    required: tuple[LiteralClause, ...] = ()
    excluded: tuple[LiteralClause, ...] = ()

    def confidence(self, text: str) -> float:
        body = text.lower()
        if self.required or self.excluded:
            folded = _fold(text)
            if any(pattern.matches(folded) for pattern in self.excluded):
                return 0.0
            if not all(pattern.matches(folded) for pattern in self.required):
                return 0.0
        count = len(self.terms) + len(self.required)
        if not count:
            # Preserve the historical plain-query behavior for empty/short terms.
            return 0.25 if text.strip() else 0.0
        matched = sum(term in body for term in self.terms) + len(self.required)
        return min(1.0, max(0.05, matched / count)) if matched else 0.0


def compile_plain_query(query: str) -> LocalQuery:
    """Keep existing literal-topic ranking for callers that do not opt in."""
    return LocalQuery(terms=tuple(sorted({term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) > 2})))


def compile_local_query(query: str) -> LocalQuery:
    r"""Compile literal phrases/exclusions, failing closed on malformed syntax.

    Double quotes delimit required phrases. Prefix a clause with ``-`` to
    exclude it. Within quotes, ``\"`` and ``\\`` may be escaped with backslash.
    Embedded hyphens in ordinary terms retain their previous meaning.
    """
    if len(query) > MAX_QUERY_LENGTH:
        raise QuerySyntaxError(f"Use at most {MAX_QUERY_LENGTH} characters.")
    positive: list[str] = []
    required: list[str] = []
    excluded: list[str] = []
    cursor = 0
    clauses = 0
    while cursor < len(query):
        if query[cursor].isspace():
            cursor += 1
            continue
        clauses += 1
        if clauses > MAX_QUERY_CLAUSES:
            raise QuerySyntaxError(f"Use at most {MAX_QUERY_CLAUSES} search clauses.")
        negative = (
            query[cursor] == "-"
            and cursor + 1 < len(query)
            and not query[cursor + 1].isspace()
        )
        if negative:
            cursor += 1
        quoted = query[cursor] == '"'
        if quoted:
            cursor += 1
            characters: list[str] = []
            while cursor < len(query) and query[cursor] != '"':
                if query[cursor] == "\\" and cursor + 1 < len(query) and query[cursor + 1] in {'"', "\\"}:
                    cursor += 1
                characters.append(query[cursor])
                cursor += 1
            if cursor == len(query):
                raise QuerySyntaxError("Close the quoted phrase with a double quote.")
            cursor += 1
            if cursor < len(query) and not query[cursor].isspace():
                raise QuerySyntaxError("Separate search clauses with whitespace.")
            value = " ".join("".join(characters).split())
            if not value:
                raise QuerySyntaxError("Quoted phrases must not be empty.")
        else:
            start = cursor
            while cursor < len(query) and not query[cursor].isspace():
                cursor += 1
            value = query[start:cursor]
            if '"' in value:
                raise QuerySyntaxError("Start a quoted phrase at the beginning of a search clause.")
        if negative:
            excluded.append(value)
        elif quoted:
            required.append(value)
        else:
            positive.append(value)
    terms = compile_plain_query(" ".join(positive)).terms
    if excluded and not (terms or required):
        raise QuerySyntaxError("Add a positive search term or quoted phrase before excluding text.")
    return LocalQuery(
        terms=terms,
        required=tuple(_literal_pattern(value) for value in dict.fromkeys(required)),
        excluded=tuple(_literal_pattern(value) for value in dict.fromkeys(excluded)),
    )


def _literal_pattern(value: str) -> LiteralClause:
    value = _fold(value)
    # Only application-owned whitespace patterns are compiled. User punctuation
    # is escaped, so no user-provided SQL/regex is ever executed.
    expression = r"\s+".join(re.escape(part) for part in value.split())
    return LiteralClause(
        pattern=re.compile(expression),
        left_boundary=_word_character(value[0]),
        right_boundary=_word_character(value[-1]),
    )
