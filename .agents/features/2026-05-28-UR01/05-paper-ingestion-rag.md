# 05 Paper Ingestion RAG

## Feature branch

`feature/ur01-05-paper-ingestion-rag`

## Requirement mapping

Paper discovery, ingestion, summaries and retrieval-augmented answers.

## Priority

P1

## Assigned to

Senior Lead Developer

## Mission

Add read-only paper ingestion and retrieval workflow for local research notes.

## Full Context

Phase 1 can use scholarly APIs and local files, but must not execute code or mutate external systems.

## Research Findings / Implementation Direction

Keep provider adapters isolated. Store source metadata, extracted text references and generated notes locally.

## Requirements

- Add source records for URLs, PDFs and academic IDs.
- Add extraction/summarization workflow boundary.
- Add retrieval path for cited answers.
- Save structured notes and provenance.

## Atomic Steps

1. Inspect selected parser/RAG libraries.
2. Add source ingestion contracts.
3. Implement metadata and text extraction path.
4. Add summarization and retrieval workflow.
5. Test with small local fixture or mocked provider.

## Key Files

- Future source, ingestion and retrieval modules
- `.agents/DATABASE-EDR-RLS.md`

## Verification

- Lint.
- Unit tests with mocked scholarly provider.
- Manual ingest smoke test.

## Git Branching

Branch from `develop` after branch 04 merges.

## Definition of Done

Hydra can ingest a source, summarize it, retrieve relevant passages and preserve provenance locally.
