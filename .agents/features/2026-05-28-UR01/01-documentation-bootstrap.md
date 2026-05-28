# 01 Documentation Bootstrap

## Feature branch

`feature/ur01-01-documentation-bootstrap`

## Requirement mapping

Phase 1 planning, no-fork policy, local-first scope and execution memory.

## Priority

P0

## Assigned to

Senior Lead Developer

## Mission

Create Hydra planning docs that constrain Phase 1 before app code starts.

## Full Context

Hydra Phase 1 is a web-first local research companion. Upstream projects are reference-only. No forks, Hermes runtime dependency, Supabase, Electron, code execution, experiments, cloud spend or publishing.

## Research Findings / Implementation Direction

Use terse markdown docs. Keep `.agents` as source of truth for branch order, process, database planning and learned constraints.

## Requirements

- Update requirements doc to no-fork wording.
- Add learned rules, checklist, atomic structure, process flow, quick reference and database planning docs.
- Add attribution and ignore temporary upstream artifacts.

## Atomic Steps

1. Edit `Hydra - User Requirements.md`.
2. Create `.agents` docs.
3. Create all Phase 1 branch guides.
4. Add `.gitignore` and `ATTRIBUTION.md`.
5. Run verification.

## Key Files

- `Hydra - User Requirements.md`
- `.agents/**`
- `.gitignore`
- `ATTRIBUTION.md`

## Verification

- `git diff --check`
- `git status --short`

## Git Branching

Branch from `develop`. Do not push without user approval.

## Definition of Done

Docs exist, Phase 1 scope is clear, no app source files are created, verification passes.
