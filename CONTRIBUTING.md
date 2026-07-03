# Contributing to HydraLab

Thanks for your interest in HydraLab! This is a pre-release, offline-first research workbench, and contributions of all kinds are welcome — bug reports, docs, tests, and code.

Please read this guide before opening a pull request. It covers environment setup, the verification gate every PR must pass, and the project invariants that must never be broken.

## Project layout

HydraLab is a monorepo:

| Path | What it is |
| --- | --- |
| `apps/web` | React 19 + TypeScript + Vite web app (Bun workspace) |
| `apps/chrome-extension` | Chrome MV3 extension |
| `apps/desktop` | Tauri v2 desktop shell |
| `backend/hydra` | Python 3.11+ FastAPI + SQLModel + async SQLite + Alembic |

Python is managed with [`uv`](https://docs.astral.sh/uv/); JavaScript/TypeScript with [`bun`](https://bun.sh/). Development is macOS-first — other platforms may work but are not the current target.

## Getting set up

Prerequisites: Python 3.11+, `uv`, and `bun`.

```sh
# Backend dependencies
uv sync

# Frontend dependencies
bun install
```

### Running locally

Backend (binds to 127.0.0.1, auto-selects a port in 8765–8799):

```sh
cd backend
uv run python -m hydra.serve --project-root <path>
```

Frontend (Vite on http://127.0.0.1:5173):

```sh
bun run dev
```

## The verification gate

Every PR must be green on all four of these before review:

```sh
# Backend tests
uv run --project backend pytest backend/tests -q

# Web unit tests
bun test apps/web/src

# Typecheck
bun run typecheck

# Frontend build
bun run build
```

CI runs the same gate on every push and pull request, but please run it locally first — it is faster for everyone.

## Branch and PR conventions

- Branch off `develop`. `main` tracks releases; day-to-day work merges into `develop`.
- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages and PR titles, e.g. `feat(citations): add BibTeX export`, `fix(retrieval): handle empty index`.
- Keep commits small and focused. Do **not** squash-merge — we preserve commit history as-is.
- Reference the related issue in your PR description when one exists.
- Fill in the pull request template, including the testing checklist.

## Invariants you must preserve

HydraLab makes specific promises to its users. Any change that weakens one of these will not be merged, no matter how useful otherwise:

1. **No fabricated citations.** Retrieval and citation features must only surface sources that actually exist in the user's library. Never generate, guess, or "fill in" citation data that was not retrieved.
2. **Nothing leaves the machine without explicit user action.** HydraLab is offline-first. No telemetry, no background phoning home, no implicit network calls to third parties. Any network egress (e.g. to a model provider) must be the direct, visible result of a user action.
3. **Secrets live only in the OS keychain.** API keys and other credentials must never be written to config files, the SQLite database, logs, or environment files.
4. **Dependency licensing.** Every new dependency must be added to `ATTRIBUTION.md` and must pass the license gate at `scripts/license_gate.py` (exercised by `backend/tests/test_release_pipeline.py` as part of the pytest run). No AGPL- or GPL-licensed dependency may ship in a distributable build.

If you are unsure whether a change touches one of these, say so in the PR description and we will figure it out together.

## Reporting bugs and requesting features

Use the issue templates in `.github/ISSUE_TEMPLATE/`. For security vulnerabilities, do **not** open a public issue — see [SECURITY.md](SECURITY.md).

## Code of conduct

Participation in this project is governed by our [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE) that covers the project.
