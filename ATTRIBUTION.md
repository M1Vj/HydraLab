# Attribution

HydraLab is an original project that may study open-source tools and public research systems as references. Normal package dependencies are allowed when they fit the feature guide and their licenses are tracked. Upstream repositories must not be committed as forks, vendored code or copied source unless a future approved branch explicitly changes that rule and preserves license obligations.

## Reference Map

- VS Code, Cursor, Theia and FlexLayout: workbench, panel, command-palette and extension-boundary references.
- Obsidian and CodeMirror 6: Markdown editing, wikilinks, backlinks and plugin-style editor extension references.
- Zotero, Zotero Connector, Citation.js, citeproc-js, OpenAlex, Crossref, Semantic Scholar, arXiv, Unpaywall, CORE and OpenCitations: citation, source discovery, metadata, connector and bibliographic-format references.
- PDF.js, Docling, GROBID and PyMuPDF/PyMuPDF4LLM: document viewing, conversion, scholarly extraction and fallback extraction references.
- OpenPrism, DOCX/OpenXML references and related document tooling: writing, LaTeX/DOCX export and document-structure references.
- Hermes Agent: skill, memory, context-file and self-improvement concepts.
- OpenAI Codex app/browser behavior, OpenAI Agents SDK, LangGraph, PydanticAI, Pi, Odysseus, Robin, Co-Scientist, AlphaProof Nexus, MLEvolve and AutoResearchClaw: agent runtime, orchestration, ranking/evolution/cache, browser approval and autonomy workflow references.
- Tauri, Electron and platform signing/updater docs: Phase 3 packaging and update references.

## License Preservation Rule

If HydraLab copies or substantially adapts licensed code, preserve copyright notices and license text required by that project. Add file-level or document-level attribution where copied material appears.

Before using reference code directly, verify the current upstream license, compatibility with HydraLab's release posture, whether transitive dependencies are acceptable and whether a smaller clean-room implementation is safer.

## Dependency Licensing Register (spec Section 37.3–37.4, DEC-1)

This register is the operational home of the spec Section 37 dependency licensing register. Update it in the same branch that adds, removes or reclassifies a dependency. Roles: `bundled-dependency` (ships in any distributable), `optional-non-bundled` (user-installed, subprocess/service-isolated, never packaged), `dev-tool` (build/test/CI only, never shipped), `reference-only` (studied, never vendored/adapted). Bundle policy (Section 37.1, DEC-1): no strong-copyleft (AGPL/GPL) dependency may appear in any distributed or packaged build — in force from the first artifact that leaves the developer's machine.

| Name | SPDX license | Copyleft? | Role | Distribution impact | Review status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| PyMuPDF / PyMuPDF4LLM | AGPL-3.0-only / commercial (dual) | strong | optional-non-bundled | If bundled, forces AGPL on HydraLab. MUST NOT be packaged. | RED-hazard | User-installed, runtime/subprocess-isolated only (Section 37.5). NOT the default extractor; permissive light extractor is default. |
| citeproc-js | CPAL-1.0 / AGPL-3.0 (dual) | strong | reference-only | NOT bundled. Would poison the bundle (AGPL) if imported. | RED-hazard | Branch 01-09 decision (DEC-1, HL-LIC-01): NOT bundled and NOT installed. Replaced by the permissive Python processor `citeproc-py` (BSD-2-Clause-Views). Verified absent from the JS bundle: `grep -ri citeproc apps/web/dist` returns nothing. |
| Zotero translators | AGPL-3.0 | strong | reference-only | None if never copied; AGPL contamination if adapted/vendored. | RED-hazard | Studied for metadata-detection/import behavior ONLY (Section 25.5). MUST NOT adapt/copy/vendor their code into HydraLab's bundle. Phase-1 Zotero compatibility is BibTeX/CSL-JSON/RIS import+export only — no RDF, no write-back. |
| Citation.js | MIT | none | reference-only | Permissive if adopted; NOT used in Phase 1. | cleared | Branch 01-09 keeps the citation stack in Python (server-side), so Citation.js is NOT added. Its CSL rendering plugin pulls citeproc-js (CPAL/AGPL), which we avoid entirely. Format conversion is handled by `bibtexparser`/`rispy` instead. |
| OpenAI Agents SDK | Apache-2.0 | none | reference-only | Permissive if adopted; NOT added in branch 02-01. | cleared | Branch 02-01 framework spike (2026-07-02): studied for the worker/tool/guardrail/tracing runtime shape. Decision: implement HydraLab's own `Run`/`Tool`/`Skill`/`Trace`/`Artifact`/`Approval` contracts (`backend/hydra/agents/`) instead of adding the dependency, keeping public agent concepts framework-independent (Section 25.8). No runtime dependency added. |
| LangGraph | MIT | none | reference-only | Permissive if adopted; NOT added in branch 02-01. | cleared | Branch 02-01 spike: studied for durable/interruptible stage workflows (the orchestrator branch's concern, not this one). Not adopted here; no dependency added. |
| PydanticAI | MIT | none | reference-only | Permissive if adopted; NOT added in branch 02-01. | cleared | Branch 02-01 spike: studied for typed/validated structured tool outputs. Not adopted; HydraLab already validates via its own contracts + Pydantic request schemas. No new dependency. |
| Pi (earendil-works/pi) | MIT | none | reference-only | Permissive if adopted; NOT added. | cleared | Branch 02-01 spike: studied for markdown-defined agents + global/project-local skill discovery patterns. Behavior reimplemented behind HydraLab's own scoped skill registry; no code vendored. |
| Odysseus (pewdiepie-archdaemon/odysseus) | MIT | none | reference-only | Permissive if adopted; NOT added. | cleared | Branch 02-01 spike: studied for settings/memory/skill UX patterns only. Not forked/vendored (no spike-approved fork); no dependency added. |
| Docling | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Primary structured conversion (Section 25.2). ML models pre-fetched (DEC-3). |
| GROBID | Apache-2.0 | none | optional-non-bundled | Permissive — issue is WEIGHT, not license (Java/JVM service). | cleared | Optional external Docker/JVM service, deferred, behind labeled setup/disabled UI with graceful degradation (DEC-3). |
| PDF.js | Apache-2.0 | none | bundled-dependency | Permissive; ships freely. | cleared | Phase 1 PDF renderer + custom annotation layer (Section 26.4). Pin major version (DEC-15). |
| CodeMirror 6 | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Phase 1 Markdown/text editor foundation (Sections 13, 26.3). |
| Lezer / @lezer/highlight | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | CodeMirror syntax highlighting support used by the Markdown editor. |
| Monaco Editor | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Reference-first for Phase 1; ship only if a raw-code/config/LaTeX surface adopts it. |
| xterm.js | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Logs/safe-console renderer (Section 19). |
| lucide-react | ISC | none | bundled-dependency | Permissive; ships freely. | cleared | Icon set (Section 6). |
| FlexLayout (flexlayout-react) | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Docking workbench layout (Sections 4.2, 6). |
| Radix primitives | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Accessible UI primitives (Section 6). |
| shadcn | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Used as codegen patterns/components, not a fixed theme (Section 6). |
| zustand | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Workbench layout persistence store (`hydralab-workspace`) with versioned migrate fallback. |
| cmdk | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Keyboard-first command palette surface inside Radix dialog. |
| Tailwind CSS / @tailwindcss/vite | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Utility/CSS build integration for HydraLab-owned design tokens. |
| class-variance-authority | Apache-2.0 | none | bundled-dependency | Permissive; ships freely. | cleared | Small utility for variant-driven UI classes where needed. |
| clsx | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Conditional class-name utility. |
| tailwind-merge | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Tailwind class merge helper for local UI primitives. |
| @tanstack/react-virtual | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Virtualized Explorer rows for large project trees. |
| @playwright/test | Apache-2.0 | none | dev-tool | Test runner only; not shipped. | cleared | Browser E2E verification for workbench docking, persistence and command flows. |
| pypdf | BSD-3-Clause | none | bundled-dependency | Permissive; ships freely. | cleared | Default permissive text-extraction lib (Section 37.6). |
| pdfminer.six | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Default permissive text-extraction lib. |
| pdfplumber | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Default permissive text/table/page-utility lib. |
| keyring | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | OS credential storage abstraction for provider secrets; raw secrets stay out of TOML/YAML/SQLite/runtime files. License verified from installed dist-info and PyPI/docs. |
| tomli-w | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | TOML writer for `settings.toml`; paired with stdlib `tomllib` for reads. License verified from package classifier/PyPI. |
| ruamel.yaml | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Round-trip YAML loader/writer for `project.yaml` preserving unknown fields/comments, and the YAML front-matter parser for the assistant skill registry. License verified from package metadata/PyPI. |
| httpx | BSD-3-Clause | none | bundled-dependency | Permissive; ships freely. | cleared | HTTP client used by HydraLab-owned scholarly provider adapters (OpenAlex, arXiv, Crossref, Unpaywall, Semantic Scholar, CORE, OpenCitations) and by the HydraLab-owned LLM provider adapters (OpenAI API-key path, OpenRouter BYO-key), all with an injectable transport so tests never hit live APIs. License verified from installed package metadata. |
| jaraco.classes | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Transitive dependency of `keyring`; MIT classifier in installed metadata. |
| jaraco.context | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Transitive dependency of `keyring`; MIT license verified from installed dist-info license file. |
| jaraco.functools | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Transitive dependency of `keyring`; MIT license verified from installed dist-info license file. |
| more-itertools | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Transitive dependency of `jaraco.classes`/`jaraco.functools`; MIT license verified from installed dist-info license file. |
| PaperQA2 | Apache-2.0 | none | bundled-dependency (Phase 2) | Permissive; ships freely. | verify-at-adoption | Phase 2 scientific RAG (Section 25.6). Re-scan transitive tree at adoption. |
| LangGraph / PydanticAI / OpenAI Agents SDK / others | (verify at adoption) | (verify) | bundled-dependency (Phase 2) | TBD per chosen framework + its transitive tree. | verify-at-adoption | Phase 2 only. License + full transitive license tree scanned and rowed before adoption (Section 25.8). No adoption without a cleared scan. |
| citeproc-py | BSD-2-Clause-Views | none | bundled-dependency | Permissive; ships freely. | cleared | Branch 01-09 SHIPPED CSL rendering processor (HL-LIC-01). Pure-Python, permissive; the AGPL-free replacement for citeproc-js. Ships CSL locales; APA is the global default style. License verified from installed dist-info (`License: BSD-2-Clause-Views`, OSI BSD classifier). |
| bibtexparser | LGPLv3 or BSD (dual) | none (BSD term selected) | bundled-dependency | Permissive under the selected BSD term. | cleared | Pinned `==1.4.4` (v2 still beta). BibTeX parse/write behind HydraLab's `CitationFormatService`. Dual-licensed; HydraLab selects the BSD term. License verified from installed dist-info (`License: LGPLv3 or BSD`). |
| rispy | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | RIS parse/write for `CitationFormatService`. License verified from installed dist-info (OSI MIT classifier). |
| lxml | BSD-3-Clause | none | bundled-dependency | Permissive; ships freely. | cleared | Transitive dependency of `citeproc-py` (CSL/XML parsing). Branch 02-08 also uses it for OOXML comments/tracked-changes/reference parsing with a HARDENED parser (`resolve_entities=False, no_network=True, load_dtd=False`) — XXE/remote-entity resolution off (Sec 34.5); `defusedxml` was therefore NOT added. License verified from installed dist-info (`License: BSD-3-Clause`). |
| pyparsing | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Transitive dependency of `bibtexparser`. MIT license verified from PyPI/dist-info. |
| CSL styles (APA, IEEE) | CC-BY-SA-3.0 | weak (content licence, data-only) | bundled-dependency (data) | Data files, not code. Attribution preserved. | cleared | Vendored under `backend/hydra/services/citations/data/styles/` from github.com/citation-style-language/styles (CC-BY-SA-3.0). Data assets consumed by citeproc-py; NOT source code. APA is the shipped global default style; IEEE is the alternate. License URL retained inside each `.csl` `<info><rights>`. |
| python-docx | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Branch 01-12 BUNDLED DOCX read/write path (HL-EXPORT-06/07, HL-LIC-04). Pure-Python + lxml; used for import (paragraphs + core-property metadata) and export (applies effective manuscript format). Branch 02-08 additionally uses it for the AI-assisted OpenXML structural-edit path (reader model + typed apply of paragraph/run/style/table/header/footer/comment ops). No strong-copyleft in the bundled DOCX path. License verified from installed dist-info (`License: MIT`). |
| Pandoc | GPL-2.0-or-later | strong | optional-non-bundled | If bundled/linked, forces GPL on HydraLab. MUST NOT be packaged/linked. | isolate-required | Branch 01-12 OPTIONAL DOCX converter. Invoked ONLY as a separate external subprocess against a user-installed binary (mere invocation, not linking) with graceful absence — never vendored, packaged or linked (HL-LIC-04, DEC-1). Detected via `PATH`; absent by default. |
| LibreOffice (`soffice`) | MPL-2.0 | weak (file-level) | optional-non-bundled | Optional external app; not packaged. | isolate-required | Branch 01-12 OPTIONAL DOCX converter adapter. Invoked only as an external subprocess against a user-installed LibreOffice; never bundled/linked. |

| MCP Python SDK (`modelcontextprotocol/python-sdk`) | MIT | none | reference-only | Studied for protocol shape; NOT vendored. | cleared | Branch 02-02 studied the MCP `initialize`/`tools/list`/`tools/call` request shape but implements a HydraLab-owned client (`backend/hydra/tools/mcp/`) over the wire protocol rather than vendoring the SDK, avoiding a transitive-tree re-scan. If the SDK is ever bundled, reclassify to `bundled-dependency` and scan its full transitive tree first. |
| Model Context Protocol spec (`modelcontextprotocol.io`) | CC-BY-4.0 (spec text) | none | reference-only | Protocol specification, not code. | cleared | Branch 02-02 protocol reference; no code or data vendored. |

Register invariants (Section 37.3, DEC-1): every dependency that is imported, invoked or studied appears in exactly one row; no row with Role `bundled-dependency` may have Copyleft? `strong`; every `strong` row must have Role `optional-non-bundled` or `reference-only` and Review status `RED-hazard` or `isolate-required`; `verify-at-adoption` rows must be re-scanned (package + transitive tree) and reclassified before adoption.

## CI License-Scan Gate (spec Section 37.2 — intent)

Before any distributable artifact is produced (and on every push that changes a dependency manifest), CI runs an automated license scan on both dependency trees:

- Python: `pip-licenses` emitting machine-readable JSON keyed by package and SPDX identifier.
- JS/TS: `license-checker` (or an SPDX-aware equivalent) emitting JSON keyed by package and SPDX identifier.
- Allowlist SPDX ids: MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, MPL-2.0 (file-level), CPAL-1.0 only when isolated/unmodified per Section 37.5.
- Denylist SPDX ids: AGPL-3.0-only, AGPL-3.0-or-later, GPL-2.0-*, GPL-3.0-*, and any dual license whose only selectable term is strong-copyleft for HydraLab's use.
- The gate FAILS the build if any package classified `bundled-dependency` resolves to a denylist SPDX id.
- An unknown/unrecognized SPDX id FAILS the gate as "unreviewed" rather than passing silently.
- `optional-non-bundled` and `reference-only` entries are excluded from the bundled scan scope only via an explicit, reviewed exception list citing their register row and isolation justification.
- Scanner config and allow/deny lists are HydraLab-owned trusted config under version control; gate output is retained as release verification evidence.

The executable gate lands with the first release/distributable branch; this register and gate intent are binding from day one because distributing even one beta build triggers copyleft obligations (Section 37.7).
