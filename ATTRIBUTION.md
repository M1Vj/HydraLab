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
| citeproc-js | CPAL-1.0 / AGPL-3.0 (dual) | strong | optional-non-bundled | AGPL branch poisons bundle; CPAL branch usable only unmodified + isolated + attribution. | RED-hazard | Use ONLY unmodified under CPAL, isolated (subprocess/embedded JS sandbox), CPAL attribution preserved; otherwise replace with a permissive CSL path. |
| Zotero translators | AGPL-3.0 | strong | reference-only | None if never copied; AGPL contamination if adapted/vendored. | RED-hazard | Studied for metadata-detection/import behavior ONLY (Section 25.5). MUST NOT adapt/copy/vendor their code into HydraLab's bundle. |
| Citation.js | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | WARNING: its CSL rendering plugin pulls citeproc-js (CPAL-1.0/AGPL-3.0). Use Citation.js for DOI/BibTeX/CSL JSON/RIS conversion; route CSL rendering through the isolated permissive CSL path, not an auto-pulled citeproc-js bundle. |
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
| pypdf | BSD-3-Clause | none | bundled-dependency | Permissive; ships freely. | cleared | Default permissive text-extraction lib (Section 37.6). |
| pdfminer.six | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Default permissive text-extraction lib. |
| pdfplumber | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Default permissive text/table/page-utility lib. |
| keyring | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | OS credential storage abstraction for provider secrets; raw secrets stay out of TOML/YAML/SQLite/runtime files. License verified from installed dist-info and PyPI/docs. |
| tomli-w | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | TOML writer for `settings.toml`; paired with stdlib `tomllib` for reads. License verified from package classifier/PyPI. |
| ruamel.yaml | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Round-trip YAML loader/writer for `project.yaml` preserving unknown fields/comments. License verified from package metadata/PyPI. |
| httpx | BSD-3-Clause | none | bundled-dependency | Permissive; ships freely. | cleared | HTTP client used by HydraLab-owned scholarly provider adapters for OpenAlex, arXiv, Crossref, Unpaywall, Semantic Scholar, CORE and OpenCitations. License verified from installed package metadata. |
| jaraco.classes | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Transitive dependency of `keyring`; MIT classifier in installed metadata. |
| jaraco.context | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Transitive dependency of `keyring`; MIT license verified from installed dist-info license file. |
| jaraco.functools | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Transitive dependency of `keyring`; MIT license verified from installed dist-info license file. |
| more-itertools | MIT | none | bundled-dependency | Permissive; ships freely. | cleared | Transitive dependency of `jaraco.classes`/`jaraco.functools`; MIT license verified from installed dist-info license file. |
| PaperQA2 | Apache-2.0 | none | bundled-dependency (Phase 2) | Permissive; ships freely. | verify-at-adoption | Phase 2 scientific RAG (Section 25.6). Re-scan transitive tree at adoption. |
| LangGraph / PydanticAI / OpenAI Agents SDK / others | (verify at adoption) | (verify) | bundled-dependency (Phase 2) | TBD per chosen framework + its transitive tree. | verify-at-adoption | Phase 2 only. License + full transitive license tree scanned and rowed before adoption (Section 25.8). No adoption without a cleared scan. |

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
