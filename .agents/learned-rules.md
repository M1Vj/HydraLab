# Hydra Learned Rules

## 1. Architecture

1.1. No forks. T3 Code, Hermes Agent and similar upstream projects are temporary references only. Rewrite or adapt needed ideas into Hydra-owned components.

1.2. Remove temporary upstream downloads after reference use. Do not commit clone artifacts, vendored upstream repos or generated reference dumps.

1.3. Phase 1 is web-first and local-first. Use local SQLite. Defer Supabase, Electron, code execution, experiments, cloud spend and publishing.

1.4. Phase 1 must not require Hermes at runtime. Hermes may inspire skills, memory and workflow design, but Hydra owns the implementation.

## 2. Attribution

2.1. Keep `ATTRIBUTION.md` current when upstream code, design patterns or algorithms influence Hydra.

2.2. If substantial MIT-licensed code is copied or adapted, preserve license text and copyright notices in the relevant files or attribution docs.

## 3. Workflow

3.1. Work from `develop` using feature branches named in `.agents/features/**`.

3.2. Mark `.agents/checklist.md` items complete only after branch implementation, verification and merge back into `develop`.

3.3. Do not push unless user explicitly asks.

3.4. Do not revert edits made by others. Inspect working tree before changing files and keep scope tight.

## 4. Verification

4.1. Run branch-specific verification from its feature guide before handoff.

4.2. For documentation/bootstrap changes, run `git diff --check` and `git status --short`.
