# 04 Chat Status Orchestration

## Feature branch

`feature/ur01-04-chat-status-orchestration`

## Requirement mapping

Conversational research and transparent status updates.

## Priority

P0

## Assigned to

Senior Lead Developer

## Mission

Implement chat thread persistence and status events for read-only research workflows.

## Full Context

Hydra must show what it is doing: searching, reading, citing, rewriting and saving.

## Research Findings / Implementation Direction

Model status as first-class messages or linked events so trace remains searchable.

## Requirements

- Create conversations and messages.
- Add status event stream.
- Persist chat and status history in SQLite.
- Add provider boundary without hard-coding one vendor.

## Atomic Steps

1. Define chat/status data contracts.
2. Implement local persistence hooks/services.
3. Add chat UI send/receive states.
4. Add status rendering.
5. Test persistence and UI states.

## Key Files

- Future chat modules
- SQLite access layer

## Verification

- Lint.
- Unit tests for chat persistence.
- Browser smoke test for send/status flow.

## Git Branching

Branch from `develop` after branch 03 merges.

## Definition of Done

Chat and status events persist locally and render clearly with no code execution paths.
