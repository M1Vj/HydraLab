# 02 Local SQLite Foundation

## Feature branch

`feature/ur01-02-local-sqlite-foundation`

## Requirement mapping

Local persistence for Phase 1 workspace state.

## Priority

P0

## Assigned to

Senior Lead Developer

## Mission

Implement local SQLite schema and data access contracts for chats, notes, tasks, sources, citations and settings.

## Full Context

Phase 1 cannot depend on Supabase or Hermes memory. SQLite is local source of truth.

## Research Findings / Implementation Direction

Keep schema small and migration-friendly. Store traceability links between claims, evidence and notes from start.

## Requirements

- Add local database initialization.
- Add migrations for entities listed in `.agents/DATABASE-EDR-RLS.md`.
- Add typed access layer matching app conventions.
- Add seed/dev workspace if project pattern supports it.

## Atomic Steps

1. Inspect project stack.
2. Add SQLite dependency using existing package manager.
3. Implement migrations and access layer.
4. Add focused tests for create/read/update paths.
5. Update database doc if schema differs.

## Key Files

- `.agents/DATABASE-EDR-RLS.md`
- Future app database modules

## Verification

- Package manager install check.
- Lint.
- Database unit tests.
- Migration smoke test.

## Git Branching

Branch from `develop` after branch 01 merges.

## Definition of Done

SQLite initializes locally, core entities persist, tests pass and docs match schema.
