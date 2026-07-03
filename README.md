<h1 align="center">HydraLab</h1>

<p align="center">
  <strong>An offline-first research workbench for reading, citing, writing, and running research agents — entirely on your own machine.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-macOS-lightgrey" alt="macOS">
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white" alt="React 19">
  <img src="https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/status-pre--release-orange" alt="Pre-release">
</p>

<p align="center">
  <img src="docs/hydralab-workbench.png" alt="The HydraLab workbench: dockable panels for sources, PDF reading, annotations, and tasks" width="100%">
</p>

HydraLab is a project-centered local app: you open a folder and work with papers, notes, citations, browser context, saved chats, claims, evidence links, tasks, drafts, exports, and orchestrated research agents — all backed by files and a per-project SQLite database on your disk.

It is **not** a VS Code, Theia, Obsidian, Zotero, or co-scientist fork. It uses proven open-source libraries and reference implementations, then adapts the useful ideas through HydraLab-owned architecture and contracts.

## Why HydraLab

- **Local and private by default.** Your papers, notes, and data live on your machine. Nothing leaves it without an explicit action from you. API keys are stored in the OS keychain, never in the project.
- **Honest by construction.** Retrieval returns extractive passages with source locators (page, section, offset) and never fabricates citations or references.
- **A real workbench, not a demo.** A dockable, VS Code–style workspace where every panel is wired to a live backend — reading, annotating, citing, writing, chatting, searching, and organizing all in one place.
- **Assistants and autonomy, gated.** Optional assistant recipes and closed-loop agents run behind consent, approvals, a Review Inbox, safety checkpoints, and an append-only audit ledger.

## Features

**Workbench & editing**
- VS Code–style dockable panels (FlexLayout) with drag/close/rearrange and named, per-project persisted layouts
- Command palette, keyboard navigation, and error-isolated panels
- CodeMirror 6 Markdown editor with wikilinks, backlinks, callouts, and live preview
- PDF.js reader with a research annotation layer (text-layer selection highlights stored in normalized page coordinates)

**Sources, citations & evidence**
- Source discovery through scholarly APIs (OpenAlex, Crossref, arXiv, and more)
- Document ingestion (Docling + a permissive light extractor) with an async ingestion queue and a local search index
- Citations, claims, and evidence links with BibTeX / CSL-JSON / RIS import & export and APA/IEEE rendering (permissive CSL via `citeproc-py`)
- Confidence-based duplicate detection and source merge with referential-integrity repair

**Assistant, agents & MCP**
- Per-project named chats with bring-your-own-key providers (OpenAI, OpenRouter) and a token budget
- MCP tool support, orchestrated recipes (literature review, paper critique, idea generation), and traceable staged agent runs with approvals
- Skills registry and project-local assistant context (`HYDRA.md`), consent-gated and Review-Inbox routed

**Autonomy, reproducibility & collaboration**
- Closed-loop autonomy with policy gates, risk classification, safety checkpoints, and an append-only audit ledger
- Sandboxed experiment execution and a reproducibility/evaluation ledger
- Real-time collaborative editing (Yjs) with a durable, replayable update log
- Responsive mobile/tablet layouts and a Tauri desktop packaging shell (pre-release)

## Tech stack

| Layer      | Stack |
| ---------- | ----- |
| Frontend   | React 19, TypeScript, Vite, FlexLayout, CodeMirror 6, PDF.js |
| Backend    | Python 3.11+, FastAPI, SQLModel, async SQLite (aiosqlite), Alembic |
| Storage    | Per-project SQLite + readable project files; secrets in the OS keychain |
| Desktop    | Tauri v2 (packaging shell, pre-release) |
| Extension  | Chrome MV3 browser bridge |

## Getting started

### Prerequisites

- **macOS** (Apple Silicon or Intel)
- **Python 3.11+** and [uv](https://docs.astral.sh/uv/)
- **[Bun](https://bun.sh) 1.x** (JavaScript runtime + workspace manager)
- *(optional)* A Rust toolchain if you want to build the Tauri desktop shell

### Installation

```bash
git clone https://github.com/M1Vj/HydraLab.git
cd HydraLab

uv sync        # backend (Python) environment
bun install    # frontend workspace (apps/*)
```

### Running HydraLab

HydraLab runs as a local backend plus a web frontend. Start each in its own terminal.

```bash
# 1) Backend — binds 127.0.0.1 and auto-selects a port in 8765–8799
cd backend
uv run python -m hydra.serve --project-root /path/to/your/research-project
```

```bash
# 2) Frontend — Vite dev server on http://127.0.0.1:5173
bun run dev
```

Then open <http://127.0.0.1:5173>. The dev server proxies API and WebSocket calls to the backend, so the frontend always talks to a same-origin `/api` path.

## Development

```bash
uv run --project backend pytest backend/tests -q   # backend test suite
bun test apps/web/src                              # web unit tests
bun run typecheck                                  # TypeScript type check
bun run build                                      # production frontend build
```

## Project structure

```
apps/web               React + TypeScript + Vite workbench (FlexLayout panels)
apps/chrome-extension  Chrome MV3 browser bridge for capturing sources
apps/desktop           Tauri v2 desktop packaging shell (pre-release)
backend/hydra          FastAPI + SQLModel backend, per-project SQLite, Alembic
scripts/               release + license-gate tooling
```

## Privacy & trust

HydraLab is designed for researchers who need to keep control of their material:

- **Offline-first.** All indexing, reading, and storage happen locally. An enforced offline-only mode hard-blocks network egress.
- **Explicit egress.** Provider calls, source downloads, and browser context sharing are consent-gated; untrusted content (page/PDF/Markdown) is treated as data, never as instructions, and can never silently trigger a fetch or write.
- **No invented sources.** Extractive retrieval quotes indexed passages verbatim with locators; it will not synthesize a citation it cannot ground.
- **Secrets stay in the keychain.** API keys are write-only from the UI and never exported or logged.

## Roadmap

HydraLab is built in three phase groups, all implemented on the `develop` branch:

1. **Research Workbench** — local workspace for reading, saving, annotating, citing, writing, searching, chatting, and organizing.
2. **Assistant / Co-Scientist** — orchestrated assistant workflows, MCP tools, recipes, approvals, and traceable agent runs.
3. **Full Autonomy** — closed-loop autonomy safety, sandboxed experiments, reproducibility ledger, real-time collaboration, mobile/tablet layouts, and a packaged macOS app with an updater.

It is **pre-release**: the macOS packaging and updater are scaffolded but not yet signed, notarized, or distributed, and MCP currently runs over the HTTP transport only. Phase 4 (open-platform interoperability, a HydraLab MCP server, and Homebrew distribution) is planned but not yet implemented.

## Third-party licenses

HydraLab depends on and studies third-party open-source software. Every dependency, its SPDX license, bundling role, and distribution impact is tracked in [`ATTRIBUTION.md`](ATTRIBUTION.md). A bundle license gate (`scripts/license_gate.py`, exercised in `backend/tests/test_release_pipeline.py`) enforces the policy that **no strong-copyleft (AGPL/GPL) dependency ships in any distributable build**.

## License

HydraLab is private while the product direction stabilizes. Its public-release timing and license are **intentionally undecided**, so no open-source license is granted yet and all rights are reserved — see [`NOTICE`](NOTICE). This deliberate posture will be replaced by a definitive license if and when one is chosen.
