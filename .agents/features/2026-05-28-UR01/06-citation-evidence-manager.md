# 06 Citation Evidence Manager

## Feature branch

`feature/ur01-06-citation-evidence-manager`

## Requirement mapping

Citation storage, claim support checks and evidence traceability.

## Priority

P1

## Assigned to

Senior Lead Developer

## Mission

Implement citation records and claim-to-evidence links so answers and drafts can be checked.

## Full Context

Hydra must reduce hallucinated citations by linking claims to source passages and metadata.

## Research Findings / Implementation Direction

Treat citations, claims and evidence links as separate entities. Keep confidence/review status explicit.

## Requirements

- Add citation CRUD.
- Add claim detection workflow boundary.
- Link claims to supporting evidence passages.
- Show unsupported or weakly supported claims in UI.

## Atomic Steps

1. Extend schema if needed.
2. Add citation/evidence services.
3. Add UI for citation details and support status.
4. Add export-ready citation shape.
5. Test claim/evidence linking.

## Key Files

- Future citation and evidence modules
- `.agents/DATABASE-EDR-RLS.md`

## Verification

- Lint.
- Unit tests for citation/evidence links.
- Browser check for support status UI.

## Git Branching

Branch from `develop` after branch 05 merges.

## Definition of Done

Claims can be linked to citations and evidence, weak support is visible, and data persists locally.
