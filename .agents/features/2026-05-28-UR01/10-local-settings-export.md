# 10 Local Settings Export

## Feature branch

`feature/ur01-10-local-settings-export`

## Requirement mapping

Local provider settings and export workflows.

## Priority

P2

## Assigned to

Senior Lead Developer

## Mission

Add local settings management and export paths for notes, citations and research traces.

## Full Context

Phase 1 keeps data local. Export is user-triggered and does not publish externally.

## Research Findings / Implementation Direction

Separate secret handling from normal settings. Prefer explicit export preview before file write.

## Requirements

- Add settings UI for providers and workspace preferences.
- Store non-secret settings locally.
- Define secret storage policy based on platform.
- Export notes, citations and task summaries.

## Atomic Steps

1. Inspect platform storage options.
2. Add settings persistence.
3. Build settings UI.
4. Add export formats.
5. Test settings and export output.

## Key Files

- Future settings and export modules
- `ATTRIBUTION.md` if upstream export/citation formats are adapted

## Verification

- Lint.
- Unit tests for settings/export.
- Browser check for settings form and export preview.

## Git Branching

Branch from `develop` after branch 09 merges.

## Definition of Done

Settings persist locally, exports are user-triggered, and no cloud publishing path exists.
