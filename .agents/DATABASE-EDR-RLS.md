# Hydra Database, EDR and RLS

## Phase 1 Database

Primary database: local SQLite.

Purpose: persist workspace state without cloud dependency.

Core entities:

- `workspaces`: local workspace metadata.
- `conversations`: chat threads and research sessions.
- `messages`: user, assistant and status messages.
- `sources`: papers, URLs, PDFs and imported source metadata.
- `notes`: structured notes, summaries and user-authored knowledge.
- `citations`: bibliographic records and source identifiers.
- `claims`: draft claims that need evidence.
- `evidence_links`: mapping between claims, citations and supporting passages.
- `tasks`: Kanban cards, status and progress metadata.
- `settings`: local provider and workspace preferences.

## EDR

EDR means entity data relationships for Hydra planning docs.

- Workspace owns conversations, notes, sources, tasks and settings.
- Conversation owns messages.
- Source may own many notes, citations and evidence links.
- Claim may link to many evidence records.
- Task may link to conversations, notes and sources.

## RLS

Phase 1 has no Supabase and no database RLS. Access control is local workspace isolation and app-level checks only.

When Supabase returns in a later phase, update this document in the same branch as backend behavior changes.

## Deferred Backend Work

No remote schema, Supabase migration, storage bucket, policy, trigger or function belongs in Phase 1.
