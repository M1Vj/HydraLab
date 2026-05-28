# 07 Writing Review Tools

## Feature branch

`feature/ur01-07-writing-review-tools`

## Requirement mapping

Grammar, style, thesis editing, LaTeX editing, PDF preview, and peer-review assistance.

## Priority

P1

## Assigned to

Senior Lead Developer

## Mission

Add draft review workflows, OpenPrism-inspired LaTeX editing, PDF preview, and peer-review for clarity, coherence, and evidence gaps.

## Full Context

Phase 1 focuses on writing support. It must explain issues, preserve user control over accepted changes, and support academic writing workflows with LaTeX and PDF preview capabilities.

## Research Findings / Implementation Direction

Keep original and revised text side by side. Implement LaTeX editor and PDF preview side-by-side in split panes. Store accepted changes and review rationale.

## Requirements

- Add writing review input with LaTeX editing support.
- Add PDF preview panel.
- Add issue categories: clarity, coherence, evidence, missing-citation, tone and unsupported claim.
- Add accept/reject revision flow.
- Persist review history.

## Atomic Steps

1. Define review request/response contract.
2. Implement review service boundary and LaTeX/PDF components.
3. Build editor/revision UI supporting split panes.
4. Link missing-citations and unsupported claims to evidence manager.
5. Test review states and compile diagnostics.

## Key Files

- Future writing review, LaTeX, and PDF modules
- Citation/evidence modules

## Verification

- Lint.
- Unit tests for review transforms.
- Browser check for accept/reject flow and LaTeX/PDF rendering.

## Git Branching

Branch from `develop` after branch 06 merges.

## Definition of Done

User can edit LaTeX/Markdown, preview PDFs, review draft text, inspect suggested changes, accept revisions and save trace locally.
