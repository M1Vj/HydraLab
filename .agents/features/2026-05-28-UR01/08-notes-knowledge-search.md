# 08 Notes Knowledge Search

## Feature branch

`feature/ur01-08-notes-knowledge-search`

## Requirement mapping

Summaries, notes, local search and knowledge traceability.

## Priority

P1

## Assigned to

Senior Lead Developer

## Mission

Implement editable notes, generated summaries, backlinks and local search.

## Full Context

Hydra's memory is local. Notes must remain user-editable and linked to sources, conversations and tasks.

## Research Findings / Implementation Direction

Use simple local search first. Add richer indexing only when needed.

## Requirements

- Add notes CRUD.
- Add generated summary structure.
- Link notes to sources, chats and tasks.
- Add local search/filter UI.

## Atomic Steps

1. Implement notes data access.
2. Build notes list/detail editor.
3. Add link management.
4. Add search/filter.
5. Test persistence and search.

## Key Files

- Future note modules
- SQLite access layer

## Verification

- Lint.
- Unit tests for note links and search.
- Browser check for note editing.

## Git Branching

Branch from `develop` after branch 07 merges.

## Definition of Done

Notes are editable, searchable, linked to research context and saved in SQLite.
