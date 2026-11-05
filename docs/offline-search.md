# Narrowing an offline literature search

Saved-source retrieval accepts literal phrases and exclusions in its existing
`query` input. This applies to `GET /api/sources/retrieve` and the local retrieval
used by the literature-review recipe. Idea-generation topics retain their legacy
plain-text interpretation, without these filters. It does not change the
external scholarly discovery providers or add a new search panel.

## Examples

| Query | Meaning |
| --- | --- |
| `neural network` | Existing loose search: rank passages containing either term. |
| `"neural network"` | Require the complete phrase in a single indexed passage. |
| `"neural network" -survey` | Require the phrase and omit passages containing the word `survey`. |
| `retrieval -"case study"` | Find retrieval passages without the phrase `case study`. |
| `"neural network" "recall"` | Require both quoted phrases in the same passage. |
| `"neural network" transformer` | Require the phrase; rank passages also mentioning `transformer` higher. |
| `"AI"` | Match a short term exactly instead of the legacy loose short-query fallback. |

Pass the complete query as a URL-encoded query parameter. The existing API's
`project_id` and optional `source_id` still restrict which saved sources can be
returned. A recipe's source scope and quick/standard/deep result limit are also
unchanged.

## Matching rules and limits

- Quotes and exclusions are filters on a single extracted passage, not the entire
  source. An excluded word in a different passage does not exclude the source.
- Quoted phrases and exclusions use Unicode NFC normalization and case folding
  for matching only; returned passages and locators stay unchanged. They accept runs of whitespace,
  including line breaks. Word boundaries prevent `"network"` matching `networks`
  or `-survey` excluding `surveys`. Punctuation is literal, not a wildcard or
  regular expression. A hyphen inside a plain term such as `peer-reviewed` is
  not an exclusion operator.
- Multiple quoted phrases are all required. Plain positive terms keep their
  previous loose substring ranking; they are optional when a required phrase
  matches. Exclusions do not contribute to the ranking score. This score is
  lexical overlap, not scientific confidence or an assessment of evidence quality.
- Inside a quoted phrase, use `\"` for a literal double quote and `\\` for a
  literal backslash. Separate clauses with whitespace. Only straight double
  quotes (`"`) delimit phrases.
- Empty/unclosed quotes, clauses joined without whitespace, exclusion-only
  queries, more than 64 clauses, or more than 2,048 characters return no hits and
  an explanatory `notices` entry. Fix the query rather than silently falling back
  to a broader search. For an exclusion combined with a positive term shorter
  than three characters, quote the positive term, for example `"AI" -survey`.
- This is a small literal search syntax, not SQL, FTS5, Boolean `OR`/`NOT`, regex,
  stemming, semantic search, or a cross-passage phrase matcher. A phrase split
  across chunks cannot match. Existing plain-query tokenization, including its
  short-term fallback, is unchanged.

All matching happens locally on already indexed saved-source passages. There are
no new provider requests, downloads, dependencies, tables, settings, or consent
changes. Hits retain the original text, source/citation identifiers, chunk
identifiers, locators, extraction/index versions, and existing source scope.
Nothing is synthesized and no research conclusion is automatically written.

## Verification

```sh
uv run pytest backend/tests/test_local_query.py backend/tests/test_rag.py backend/tests/test_literature_recipe.py -q
```

Tests cover literal metacharacters and escaped quotes, multiple phrases,
exclusions, Unicode and whitespace, malformed/oversized queries, legacy ranking,
source scope, trashed/orphan sources, citation and locator preservation, the
offline semantic gate, and real upload-to-retrieval API behavior.

## Design references

SQLite's [FTS5 phrase and query documentation](https://www.sqlite.org/fts5.html#full_text_query_syntax)
provides a useful reference for explicit phrase searches. This feature deliberately
does not expose raw FTS5 syntax or change the current database/index contract.
Python's [`re.escape`](https://docs.python.org/3/library/re.html#re.escape) keeps
user punctuation literal; only application-owned whitespace and word-boundary
patterns are compiled. No third-party implementation is copied or bundled.
