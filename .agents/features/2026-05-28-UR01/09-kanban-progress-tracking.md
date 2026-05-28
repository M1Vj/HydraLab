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

Add Kanban board for research questions, writing tasks and review work.

## Full Context

Tasks should connect research activity to visible progress without hiding automation.

## Research Findings / Implementation Direction

Use stable columns first: To Do, In Progress, Review and Done. Store task links to notes, sources and conversations.

## Requirements

- Add task CRUD.
- Add column movement and ordering.
- Add progress/status metadata.
- Link tasks to notes, sources and chats.

## Atomic Steps

1. Implement task persistence.
2. Build board and card UI.
3. Add reorder/move interactions.
4. Add linked context panel.
5. Test task movement and persistence.

## Key Files

- Future task modules
- SQLite access layer

## Verification

- Lint.
- Unit tests for task ordering.
- Browser check for keyboard and pointer movement.

## Git Branching

Branch from `develop` after branch 08 merges.

## Definition of Done

Board persists tasks, movement works, progress is visible and links preserve context.
