# HydraLab

HydraLab is an offline-first research workbench for computer science and general academic papers. It is a project-centered local app where a researcher opens a folder and works with papers, notes, citations, browser context, saved chats, claims, evidence links, tasks, drafts, exports and later orchestrated research agents.

HydraLab is not a VS Code, Theia, Obsidian, Zotero or co-scientist fork. It uses proven open-source dependencies and reference implementations, then adapts the useful ideas through HydraLab-owned architecture and contracts.

## Roadmap

HydraLab is built in three phase groups. All three are now implemented on the `develop` branch:

1. Research Workbench: production-quality local workspace for reading, saving, annotating, citing, writing, searching, chatting and organizing research projects.
2. Assistant / Co-Scientist: orchestrated assistant workflows, MCP tool support, stage/agent toggles, recipes, approvals and traceable agent runs.
3. Full Autonomy: closed-loop autonomy safety, advanced customization, sandboxed experiment execution, reproducibility ledger, real-time collaboration, mobile/tablet layouts, and a packaged macOS app with an updater.

HydraLab remains desktop-first (macOS) and source/dev-run first. It is pre-release: the macOS packaging and updater are scaffolded but the app is not yet signed, notarized or distributed, and MCP runs over the HTTP transport only. Phase 4 (open-platform interoperability, a HydraLab MCP server, and Homebrew distribution) is planned but not yet implemented.

The detailed product requirements, implementation guides and per-branch execution notes are kept as internal planning documents and are not part of this repository.

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

Backend source/dev entrypoint:

```bash
python -m hydra.serve --project-root /path/to/project
```

The backend binds `127.0.0.1`, tries port `8765` first, falls back through `8799`, and writes runtime discovery files under both app data and the project's `.hydralab/runtime/` directory.

Common checks:

```bash
git diff --check
git status --short
```

Run backend/frontend tests and builds according to the feature guide being implemented.

## License

HydraLab is private while the product direction stabilizes. Public release timing and license are intentionally undecided, so no open-source license is granted and all rights are reserved (see `NOTICE`). Third-party dependency licenses are tracked in `ATTRIBUTION.md` and enforced by a bundle license gate (`scripts/license_gate.py`, exercised in `backend/tests/test_release_pipeline.py`): no strong-copyleft (AGPL/GPL) dependency may ship in a distributable build.
