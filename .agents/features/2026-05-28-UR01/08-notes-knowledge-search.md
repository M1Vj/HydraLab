# 08 Notes Knowledge Search

## Feature branch

`feature/ur01-08-notes-knowledge-search`

## Requirement mapping

Summaries, notes, local search, Obsidian-style knowledge layer, backlinks, and traceability.

## Priority

P1

## Assigned to

Senior Lead Developer

## Mission

Implement editable notes, generated summaries, backlinks, graph-like navigation, and local search.

## Full Context

Hydra's memory is local. Notes must remain user-editable and linked to sources, conversations, claims, and tasks. They should behave like an Obsidian knowledge layer where multiple views over the same research objects exist.

## Research Findings / Implementation Direction

Use simple local search first. Build a backlink index and graph-like navigation to make it clear where each idea came from.

## Requirements

- Add notes CRUD.
- Add generated summary structure.
- Link notes to sources, chats, drafts, and tasks.
- Implement Obsidian-style backlinks and graph navigation.
- Add local search/filter UI.

## Atomic Steps

1. Implement notes data access with bi-directional links.
2. Build notes list/detail editor compatible with split panes.
3. Add backlink and graph-view management.
4. Add search/filter.
5. Test persistence, links, and search.

## Key Files

- Future note and graph-view modules
- SQLite access layer

## Verification

- Lint.
- Unit tests for note links and search.
- Browser check for note editing and backlink display.

## Git Branching

Branch from `develop` after branch 07 merges.

## Definition of Done

Notes are editable, searchable, linked bi-directionally to research context, explorable via graph/backlinks, and saved in SQLite.
