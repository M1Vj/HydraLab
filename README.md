# Hydra – Web-First Research and Writing Companion

Hydra is a premium, web-first research and writing companion designed to turn literature discovery, citation management, claims verification, and academic drafting into a single, cohesive local experience. Inspired by the dynamic modular layouts of **VS Code**, the LaTeX-driven academic writing workflows of **OpenPrism**, and the interconnected knowledge mapping of **Obsidian**, Hydra establishes a robust, offline-first research workbench.

Phase 1 provides local orchestration and persistence via SQLite, featuring zero-cloud runtimes, rich local databases, SSE status event logging, paper parsing, citation graphs, and task coordination.

---

## 🌟 Core Features (Phase 1)

### 1. Modular Web Workbench (VS Code Model)
* **Activity Bar**: Quick sidebar toggles for Chat, Sources, Notes, Tasks, and Evidence.
* **Collapsible Sidebars**: Interactive list navigation, note searches, and task queues.
* **Movable Tabs & Split Panes**: Open multiple workspace modules side by side (e.g., chat beside a LaTeX draft or an Obsidian graph beside a Kanban board).
* **Integrated Bottom Panel**: Terminal displays, event stream lists, and status updates.
* **Live Status Bar**: Real-time validation metrics and current run status.

### 2. Conversational Research & Status SSE Stream (T3 Code Model)
* **Transparent Execution**: Watch Hydra work via Server-Sent Events (SSE) detailing its reasoning paths (e.g., `"searching memory..."`, `"reading pdf..."`).
* **Persistent Threads**: Full local chat history stored in SQLite.

### 3. Scholarly Ingestion & Local RAG
* **Universal Parsing**: Ingest papers from PDF files, DOIs, or URLs.
* **Local Extraction**: Under-the-hood PDF text parsing powered by `pypdf` with automated structured notes summaries generation.
* **Offline Retrieval**: Synthesizes cited workspace passages using local mock RAG vector searches.

### 4. Citation & Evidence Verification
* **Anti-Hallucination Controls**: Links claims directly to supporting source passages and confidence values.
* **Visual Verifiers**: High-fidelity sidebar **Evidence badges** indicating support levels (Green for fully supported, Yellow for weakly supported, and Red for unsupported claims).

### 5. Writing Review, LaTeX Editing & PDF Previews (OpenPrism Model)
* **LaTeX Editor**: Full LaTeX/Markdown document editor split side-by-side with dynamic PDF previews.
* **Coherence & Tone Reviews**: Interactive issue tracking checks drafts for coherence, clarity, tone, and missing citations.
* **Accept/Reject revisions**: Dynamically preview changes and cherry-pick revision edits directly inside the pane.

### 6. Obsidian-Style Knowledge Layer
* **Wiki Links**: Dynamic `[[Note Title]]` link matching automatically hooks notes, claims, tasks, and sources together.
* **Backlink Indexing**: Detailed sidebar detailing all incoming and outgoing connections for any selected note.
* **Circular SVG Local Graph**: Interactive SVG graphing displaying colored vertices representing research nodes (Indigo: notes, Emerald: sources, Amber: tasks, Rose: claims) with direct click-to-navigate graph node traversal.
* **Search Indexing**: Fast local offline searches using FTS5 fallback.

### 7. Kanban Task Management
* **Coordinate Workflows**: Visual board columns (**To Do**, **In Progress**, **Review**, **Done**) tracking active tasks, progress meters, and phase indicators.
* **Wikilink Drag Drawers**: Cards detect wiki-link text references, resolving their targets and providing quick side-drawer navigational shortcuts.
* **Native Drag & Drop**: Fluid column reordering with optimistic updates persisting to SQLite.

### 8. Provider Settings & Workspace ZIP Exports
* **Model Configurations**: Settings manager to customize OpenAI, Anthropic, and Gemini LLM provider parameters and system instructions.
* **ZIP Workspace Exporter**: Generates single-click workspace ZIP backups compressing notes, citations (.md), Kanban tasks, and raw scrubbed schemas (.json).

---

## 🛠️ Technology Stack

### Backend
* **Language/Framework**: Python 3.11+ / FastAPI
* **Database**: Local SQLite
* **ORM / Database Migrations**: SQLModel / Alembic
* **Libraries**: `aiosqlite` (async driver), `greenlet` (async thread sync), `pypdf` (PDF parsing), `httpx`

### Frontend
* **Runtime/Bundler**: Bun 1.3+ / Vite 7+
* **Framework**: React 19 / TypeScript 5
* **Icons**: `lucide-react`
* **Styling**: Vanilla CSS (highly custom, dark-theme layout)

---

## 🚀 Getting Started

### 1. Prerequisites
Ensure you have **Python 3.11+** (`uv` package manager recommended) and **Bun** (or Node/NPM) installed.

### 2. Installation

Clone the repository and install the dependencies:

```bash
# Clone the repository
git clone https://github.com/M1Vj/Hydra.git
cd Hydra

# Install Python backend dependencies using uv
uv sync

# Install Frontend dependencies using Bun
bun install
```

### 3. Running the Workspace

Start both the backend server and the frontend dev server in parallel:

```bash
# Start the FastAPI Backend (on http://127.0.0.1:8000)
cd backend
uv run uvicorn hydra.app:app --host 127.0.0.1 --port 8000

# In a new terminal window, start the React/Vite Frontend (on http://127.0.0.1:5173)
bun run dev
```

---

## 🧪 Testing and Verification

### Backend Tests
Execute the complete `pytest` test suite covering schemas, CRUD, ingestion, claims, and settings:
```bash
uv run pytest
```

### Frontend Typechecking & Compilation
Run type checks and compile production assets:
```bash
# Typecheck TypeScript files
bun run typecheck

# Compile production build
bun run build
```

---

## 📄 License
This project is private and proprietary. Refer to [ATTRIBUTION.md](file:///Users/vjmabansag/Projects/Hydra/ATTRIBUTION.md) for details on reference works, layout patterns, and scholarly guidelines.
