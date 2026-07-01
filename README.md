# HydraLab

HydraLab is an offline-first research workbench for computer science and general academic papers. It is a project-centered local app where a researcher opens a folder and works with papers, notes, citations, browser context, saved chats, claims, evidence links, tasks, drafts, exports and later orchestrated research agents.

HydraLab is not a VS Code, Theia, Obsidian, Zotero or co-scientist fork. It uses proven open-source dependencies and reference implementations, then adapts the useful ideas through HydraLab-owned architecture and contracts.

## Roadmap

HydraLab is planned in three phase groups:

1. Research Workbench: production-quality local workspace for reading, saving, annotating, citing, writing, searching, chatting and organizing research projects.
2. Assistant / Co-Scientist: orchestrated assistant workflows, full MCP support, stage/agent toggles, recipes, approvals and traceable agent runs.
3. Full Autonomy: closed-loop research workflows, advanced customization, experiment execution, collaboration, mobile/tablet support, packaged macOS app and updater.

Phase 1 is desktop-only macOS first and source/dev-run first for rapid iteration. Phase 1 has no MCP support, no autonomous research loops, no code execution, no packaged app, no mobile/tablet support and no real-time collaboration.

## Current Planning Sources

Primary living requirements:

- `HydraLab - User Requirements.md`

Implementation planning:

- `.agents/PROJECT-OVERVIEW.md`
- `.agents/00-ATOMIC-STRUCTURE.md`
- `.agents/ALL-BRANCHES-QUICK-REFERENCE.md`
- `.agents/checklist.md`
- `.agents/PROCESS-FLOW.md`
- `.agents/DATABASE-ERD-RLS.md`
- `.agents/features/`
- `.agents/learned-rules.md`

Project context and operating rules:

- `HYDRA.md`

## Architecture Direction

- Frontend: React, TypeScript and Vite.
- Backend: Python and FastAPI.
- Persistence: local project SQLite plus readable project files.
- Project config: `project.yaml`.
- Project-local assistant context: Git-tracked `HYDRA.md`.
- Global settings: app-data `settings.toml`.
- Secrets: OS credential storage.
- Workbench: custom FlexLayout-style docked panels.
- Markdown: CodeMirror 6.
- PDF: PDF.js with a custom research annotation layer.
- Ingestion: Docling (bundled default) + permissive light extractor (pypdf/pdfminer.six/pdfplumber); GROBID optional/deferred external service; PyMuPDF (AGPL) optional and never bundled.

## Development

Install dependencies and run the existing backend/frontend commands used by the repo. The current planning docs are the source of truth for implementation order and branch scope.

Common checks:

```bash
git diff --check
git status --short
```

Run backend/frontend tests and builds according to the feature guide being implemented.

## License

HydraLab is private while the product direction stabilizes. Public release timing and license are intentionally undecided. Keep attribution and third-party license tracking current before any future release decision.
