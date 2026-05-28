# 07 Writing Review Tools

## Feature branch

`feature/ur01-07-writing-review-tools`

## Requirement mapping

Grammar, style, thesis editing and peer-review assistance.

## Priority

P1

## Assigned to

Senior Lead Developer

## Mission

Add draft review workflows for clarity, coherence, evidence gaps and human-sounding prose.

## Full Context

Phase 1 focuses on writing support. It must explain issues and preserve user control over accepted changes.

## Research Findings / Implementation Direction

Keep original and revised text side by side. Store accepted changes and review rationale.

## Requirements

- Add writing review input.
- Add issue categories: clarity, coherence, evidence, tone and unsupported claim.
- Add accept/reject revision flow.
- Persist review history.

## Atomic Steps

1. Define review request/response contract.
2. Implement review service boundary.
3. Build editor/revision UI.
4. Link unsupported claims to evidence manager.
5. Test review states.

## Key Files

- Future writing review modules
- Citation/evidence modules

## Verification

- Lint.
- Unit tests for review transforms.
- Browser check for accept/reject flow.

## Git Branching

Branch from `develop` after branch 06 merges.

## Definition of Done

User can review draft text, inspect suggested changes, accept revisions and save trace locally.
