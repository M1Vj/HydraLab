# Hydra Atomic Structure

## Branch Strategy

Base branch: `develop`

Phase 1 feature branches:

1. `feature/ur01-01-documentation-bootstrap`
2. `feature/ur01-02-local-sqlite-foundation`
3. `feature/ur01-03-web-shell-research-workspace`
4. `feature/ur01-04-chat-status-orchestration`
5. `feature/ur01-05-paper-ingestion-rag`
6. `feature/ur01-06-citation-evidence-manager`
7. `feature/ur01-07-writing-review-tools`
8. `feature/ur01-08-notes-knowledge-search`
9. `feature/ur01-09-kanban-progress-tracking`
10. `feature/ur01-10-local-settings-export`

## Merge Order

Merge in numeric order. Later branches may read contracts from earlier branches but must avoid broad rewrites.

## Execution Boundary

Phase 1 builds Hydra-native web and local SQLite capabilities only. No forks, Hermes runtime dependency, Supabase, Electron, experiment execution, cloud spend or publishing.

## Verification Gates

Each branch must pass its guide verification before merge. Documentation-only branches must pass `git diff --check` and `git status --short`. App branches must also pass lint, tests and visual UI checks.

## Checklist Rule

Update `.agents/checklist.md` only after branch is implemented, verified and merged into `develop`.
