# 09 Kanban Progress Tracking

## Feature branch

`feature/ur01-09-kanban-progress-tracking`

## Requirement mapping

Task management and progress tracking.

## Priority

P2

## Assigned to

Senior Lead Developer

## Mission

Add Kanban board as a workbench component for research questions, writing tasks and review work.

## Full Context

Tasks should connect research activity to visible progress without hiding automation. The Kanban board is not a separate fixed page; it is a modular component that opens as a tab or side panel, allowing tasks to sit beside sources, notes, or chat threads.

## Research Findings / Implementation Direction

Use stable columns first: To Do, In Progress, Review and Done. Store task links to notes, sources and conversations. Ensure the board can render efficiently in a split pane.

## Requirements

- Add task CRUD.
- Add column movement and ordering.
- Add progress/status metadata and phase indicators.
- Link tasks to notes, sources and chats.
- Implement board as a flexible pane/tab component.

## Atomic Steps

1. Implement task persistence.
2. Build board and card UI designed for split panes.
3. Add reorder/move interactions.
4. Add linked context panel.
5. Test task movement and persistence in various layout states.

## Key Files

- Future task modules
- SQLite access layer

## Verification

- Lint.
- Unit tests for task ordering.
- Browser check for keyboard and pointer movement in narrow/wide panes.

## Git Branching

Branch from `develop` after branch 08 merges.

## Definition of Done

Board persists tasks, movement works, progress is visible, links preserve context, and the board renders effectively as a modular workbench component.
