# Hydra Phase 1 Process Flow

## Core Loop

1. User opens local Hydra web workspace.
2. Hydra loads local SQLite workspace state.
3. User asks research question, uploads/links source, edits note or moves task.
4. Hydra records intent, runs read-only retrieval or writing workflow, and streams status updates.
5. Hydra stores answer, notes, citations, evidence links and task progress locally.
6. User reviews, edits, exports or continues work.

## Research Flow

Question -> source discovery -> retrieval -> evidence extraction -> cited answer -> saved notes.

## Writing Flow

Draft text -> issue detection -> rewrite suggestions -> claim support check -> accepted revision -> saved trace.

## Task Flow

Idea -> Kanban card -> status updates -> linked notes/sources -> review -> done.

## Local Data Rule

SQLite is Phase 1 source of truth for chats, notes, tasks, citations, source metadata and settings references. External services are read-only providers unless user explicitly triggers an allowed export.

## Deferred Work

Supabase sync, Electron packaging, code execution, experiment runners, cloud compute and publishing workflows start after Phase 1.
