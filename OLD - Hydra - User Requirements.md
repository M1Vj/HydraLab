# Hydra Research Assistant – Phased User Guide

## Vision

Hydra is a **personal research assistant** that learns from proven open-source research and agent tools while remaining its own codebase. Rather than attempting to deliver every capability at once, Hydra evolves through a series of **phases**. Each phase is designed to be fully usable on its own and introduces new functions through built-in Hydra components. When the user mentions other projects like T3 Code, Hermes Agent, MLEvolve or Co-Scientist, the intent is to use them as temporary references or inspirations, then rewrite/adapt needed ideas into Hydra with correct attribution. Hydra is not a fork, wrapper or runtime sub-component of those upstream projects.

Hydra owns its core infrastructure: local persistence, tool boundaries, research workflows, experiment execution, multi-agent hypothesis exploration and paper generation. Hermes Agent remains a reference for persistent memory, skills and tool integration ideas[1], not a runtime base. Throughout these phases Hydra keeps **user control** and **ethics** front and centre. You decide when to run code, spend money or publish results; Hydra does not take irreversible actions without your approval.

## Phase 1 – Research Companion

### Purpose

The first phase transforms Hydra into a **web-first research and writing companion** with a polished desktop-class local UI. If you’ve used the thesis-assistant prompt previously, Phase 1 aims to meet or exceed its capabilities: it helps you discover literature, critique and polish your writing, manage your tasks and organise knowledge. This phase uses local SQLite persistence and does **not** run code, experiments, Supabase, Electron, cloud compute or publishing workflows yet; it focuses on information retrieval and writing support.

### User Experience

**Hydra-native interface inspired by T3 Code.** To provide a responsive interface quickly, Hydra may temporarily download and study T3 Code as a reference for interaction patterns and layout ideas[2]. Hydra must not fork it or depend on it at runtime. Relevant UI concepts are rewritten as built-in Hydra components: the editor pane becomes a chat and note workspace, the side panel hosts a Kanban board, and status areas show search and writing progress.

**Hydra-native agent and memory layer.** Phase 1 ships with Hydra's own local orchestration and persistence rather than requiring an existing Hermes installation. Hermes Agent may be used as a temporary reference for skill-system and memory ideas[1], but Hydra must not run as a Hermes sub-component in Phase 1. Local SQLite stores chats, notes, tasks, citations and source metadata so the assistant remembers what you’ve discussed and can revisit it later.

### Capabilities

**Conversational research.** In the chat panel you can ask Hydra to look up topics, compare studies or summarise uploaded PDFs. Hydra calls **retrieval‑augmented question‑answering** libraries such as PaperQA and PaperQA2 (open‑source agents for high‑accuracy RAG over PDFs) to find relevant passages. The assistant then composes a concise answer with citations. When summarising, Hydra extracts key findings, methods and limitations; it doesn’t hallucinate facts.

**Grammar, style and thesis editing.** Paste a paragraph or section of your thesis and ask Hydra to improve it. Drawing on the thesis‑assistant guidelines (IELTS writing criteria, humaniser patterns and grammar rules), Hydra rewrites sentences to improve clarity, coherence and flow. It flags unsupported claims, vague terminology and overly robotic phrasing, and suggests revisions. You can ask Hydra to act as a peer reviewer: it will evaluate how an examiner might perceive your argument, highlight gaps and propose improvements.

**Citation and evidence management.** Hydra automatically spots statements that need support. It searches scholarly databases via openalex and simple-arxiv, retrieves open-access versions via Unpaywall, and proposes citations. It verifies that each citation actually supports the claim, echoing the anti-hallucination and claim-verification logic in AutoResearchClaw[5]. Citations are stored in Hydra's local SQLite database and can be exported as a bibliography later.

**Summarisation and note‑taking.** Hydra can ingest papers and produce structured notes: abstracts, key takeaways, methods, results and critiques. Notes live in your knowledge base and are searchable. You can create your own notes or edit Hydra’s notes directly in the UI. Hydra also supports summarising your own drafts or meeting transcripts.

**Task management and progress tracking.** A Kanban board helps you organise work. Each research question, writing task or experiment idea becomes a card. Columns such as “To Do”, “In Progress”, “Review” and “Done” let you visualise progress. Hydra moves cards automatically as it completes sub‑tasks; you can reorder and comment on cards. Each card displays a progress bar and a phase indicator (“retrieving sources”, “summarising papers”, “drafting report”), along with time spent and number of sources consulted.

**Live chat and status updates.** The chat feed shows all conversation with Hydra. It is not a black box: Hydra posts status updates—like “searching literature”, “finding citations”, “rewriting paragraph”—so you can follow its reasoning. You can intervene at any point, ask clarifying questions, or add instructions. Even if you choose to let Hydra work autonomously, you’ll see a running commentary of its actions.

**Notes & traceability.** Every research activity is logged. Hydra stores your queries, its answers, the sources it cited, and the notes it created. You can search and filter this history to see where information came from. Persistent memory means you can close the app and return later without losing context[4].

### Under the Hood

Phase 1 uses only read-only research tools: it does not execute code or modify external systems. When Hydra needs to access a restricted API (e.g. OpenAI or Claude) it prompts you for credentials and stores local configuration according to the app's settings policy. Hydra uses the following open-source elements as references or rewritten integrations:

- **T3 Code interface** — temporary reference for layout and interaction ideas; no fork or runtime dependency[2].
- **Hermes Agent** — temporary reference for skill and memory concepts; no Phase 1 runtime dependency[1].
- **PaperQA/PaperQA2 retrieval agents** — used to fetch and summarise scientific papers through Hydra-owned integration boundaries.
- **Humaniser guidelines and grammar tools** — adopted from the thesis‑assistant system prompt for rewriting and editing.
- **AutoResearchClaw’s claim‑verification logic** — informs citation checking and anti‑hallucination behaviour[5].

### Getting Started

1. **Run Hydra locally.** Start the web app from the Hydra repository once Phase 1 implementation exists.
2. **Create a local workspace.** Hydra initializes a local SQLite database for chats, notes, tasks, citations and source metadata.
3. **Authenticate providers.** On first run, Hydra prompts you to supply API keys for model providers (OpenRouter, OpenAI, Claude, Gemini) and academic databases according to the local settings policy.
4. **Start researching.** Use the chat to ask questions, paste drafts for feedback, create tasks on the Kanban board and review the notes Hydra produces.

## Phase 2 – Experimentation Platform

### Purpose

Phase 2 expands Hydra from a research‑only tool into an **experimentation platform**. You can run code, analyse datasets and train machine‑learning models without leaving the UI. The focus is on making experiments accessible, reproducible and safe. At this stage Hydra does **not** yet generate hypotheses autonomously; you still define the questions and methods, but it takes care of execution and analysis.

### User Experience

**Compute broker.** Hydra introduces a compute broker that decides where to run tasks. You can register multiple back‑ends: your Mac, an Azure VM, a GPU server, or free services like Colab or Hugging Face ZeroGPU. Hydra selects a backend based on requirements, availability and budget. Each backend is configured via a simple form: for cloud services, you enter credentials and choose region and instance type; for Colab or ZeroGPU, Hydra will open a notebook session and manage the connection. Note that Google Colab’s free tier does not guarantee resources and forbids bypassing the notebook UI or remote shells[6]; Hydra respects these restrictions and warns you when a task may exceed quotas.

**Cloud setup agent.** Adding a new backend is guided. Hydra’s cloud setup agent creates the necessary environment, installs dependencies, runs a smoke test and reports readiness. You never have to SSH into machines manually; Hydra does it for you. Credentials are stored through Hydra's approved secret-storage layer, and you can revoke them at any time.

**Experiment runner.** Once compute is available, Hydra can run experiments. You describe the task (“train a classifier on dataset X using algorithm Y”), and Hydra orchestrates environment setup, code execution, logging and result collection. Instead of building an experiment engine from scratch, Hydra adapts **MLEvolve**, an open‑source system that uses progressive Monte‑Carlo Graph Search and experience‑driven memory to optimise machine‑learning algorithms[7]. The relevant parts—automatic hyperparameter search, branch exploration, cross‑branch fusion and memory reuse—are rewritten as Hydra-owned experiment modules and exposed via the UI. You still choose the objective and dataset; Hydra takes care of search and execution.

### Capabilities

**Experiment design assistance.** Based on the literature you retrieved in Phase 1, Hydra can suggest datasets, baseline models and evaluation metrics for your problem. It identifies existing benchmarks and proposes a plan. It uses MLEvolve’s planning logic to explore the search space[7], but you remain in control of the scope and budget.

**Code execution and monitoring.** Hydra runs experiments in isolated environments (e.g. containers on your local machine or remote VM). Logs, metrics and intermediate outputs stream back to the UI. If an experiment fails, Hydra analyses the error and suggests fixes or alternative approaches. You can pause, resume or cancel a run at any time.

**Results analysis.** After a run completes, Hydra summarises results: it plots learning curves, compares models and calculates statistics. It interprets whether the result meets your expectations and highlights anomalies. Results are stored and can be exported along with code and configuration for reproducibility.

**Compute management UI.** A new “Compute” page lists your back‑ends with status (online/offline), resource usage and cost. You can add or remove back‑ends, set budget limits and view running jobs. Each experiment has its own dashboard showing progress and metrics.

### Under the Hood

Phase 2 reuses and rewrites the following components:

- **Compute broker logic** — inspired by open-source frameworks like Modal and Daytona but implemented as Hydra-owned modules so you can swap providers easily.
- **MLEvolve experiment search** — core algorithms for Monte‑Carlo Graph Search, cross‑branch fusion and experience‑driven memory are extracted and reimplemented inside Hydra[7].
- **Cloud setup scripts** — custom code that boots instances, installs dependencies and verifies connectivity, drawing on best practices from open‑source DevOps tools.

### Getting Started

1. **Upgrade Hydra.** Install Phase 2 from the Hydra repository. Ensure Phase 1 is already running.
2. **Register compute back‑ends.** In the Compute page, add your Mac (local), your Azure VM or another remote server. You can also connect to a Google Colab notebook or a Hugging Face ZeroGPU space, but be aware of resource limits[6][8].
3. **Design an experiment.** Use the chat or Experiment page to describe what you want to test. Hydra proposes a plan; you approve or modify it.
4. **Run and monitor.** Start the experiment; watch logs and metrics in real time. Once complete, review the summary and decide next steps.

## Phase 3 – Hypothesis Studio

### Purpose

Phase 3 connects literature and experimentation into a **closed‑loop research pipeline**. Instead of you manually proposing hypotheses, Hydra now helps generate and refine them. This phase draws inspiration from **Co‑Scientist**, a multi‑agent system from DeepMind that orchestrates Generation, Proximity, Reflection, Ranking and Evolution agents[9]. Hydra reimplements these ideas to suit our context: hypotheses are grounded in the literature you’ve read, experiments are designed and executed automatically, and results feed back into hypothesis refinement.

### User Experience

**Hypothesis engine.** At the core is a supervisor agent that coordinates several specialised agents:

- **Generation agent** proposes initial hypotheses based on topics of interest and retrieved literature.
- **Proximity agent** groups similar hypotheses to ensure diversity, so the system explores different directions[10].
- **Reflection agent** acts like a peer reviewer: it critiques hypotheses, points out weaknesses and suggests improvements[10].
- **Ranking agent** holds a tournament of ideas: hypotheses debate each other in pairs, and the ranking is updated using a system like Elo or Bradley‑Terry[11].
- **Evolution agent** refines the top hypotheses by combining or modifying them; it may suggest new experiments[9].

All of these agents are implemented as Hydra-owned skills. They do not operate blindly: they refer back to your literature notes and experiment results. The idea is to mimic how a team of researchers would brainstorm, review and prioritise hypotheses.[11] emphasises that Co-Scientist invests compute into verifying claims against literature and data; Hydra copies this ethos by cross-checking each hypothesis with your sources and previous experiments.

### Capabilities

**Idea generation and clustering.** You can initiate a “hypothesis session” on a given question (“Could technique X improve outcome Y?”). Hydra’s generation agent proposes multiple ideas. The proximity agent then clusters similar ideas and selects a diverse set for further evaluation. This prevents the system from getting stuck in one neighbourhood of the idea space.

**Peer review and ranking.** For each idea, the reflection agent writes a critique: Does the idea contradict known results? Is it novel? Are there easier alternative explanations? These critiques accompany the hypotheses on a board. The ranking agent then runs pairwise debates: two hypotheses are presented, along with their critiques and any supporting literature, and the ranking is updated accordingly[11]. You can read the debates in a log to see the reasoning.

**Evolution and experiment design.** The best ideas are refined by the evolution agent: it merges related ideas, splits overly broad ones, or proposes slight tweaks. For each promising hypothesis, Hydra designs an experiment using the Phase 2 experiment runner, executes it, analyses the results and feeds them back. The cycle repeats: results inform new critiques, which influence ranking and evolution. You can set budgets, time limits or manual checkpoints (gate‑only, checkpoint or co‑pilot modes as in AutoResearchClaw[5]) to control how autonomous this process is.

### User Interface

- **Idea board.** A board lists all current hypotheses with their score, status and supporting evidence. You can click a card to see the generation history, critiques, debate transcripts and experiment results. You can also manually promote, demote or merge ideas.
- **Debate and critique logs.** Hydra logs all reflections and debates. Reading them helps you understand why a hypothesis is favoured or discarded. This transparency is crucial for trust.
- **Evolution timeline.** A timeline visualises how hypotheses evolve: splits, merges and refinements are shown as branches. You can roll back or explore alternate branches.

### Under the Hood

Hydra reimplements the Co-Scientist multi-agent framework as Hydra-owned skills: the supervisor orchestrates state transitions; each specialised agent is a small language-model prompt plus some retrieval logic. Ranking uses a pairwise judging mechanism reminiscent of idea tournaments[11]. Novelty checks rely on your literature notes and external search to ensure ideas are not obvious or redundant.

### Getting Started

1. **Ensure Phase 2 is active.** Hypothesis sessions rely on the experiment runner to test ideas.
2. **Start a session.** Use the UI to create a new hypothesis session; specify the research question and any initial constraints. Hydra will begin generating and clustering ideas.
3. **Review and approve.** You can let Hydra run through ranking cycles automatically or step in to adjust scores and critiques. Choose promising ideas to test, and Hydra will design experiments accordingly.

## Phase 4 – Manuscript Creator

### Purpose

In Phase 4 Hydra becomes a **manuscript creator**. After generating hypotheses, running experiments and analysing results, Hydra helps you turn these findings into a structured paper. The goal is not to fully automate authorship but to draft a well‑structured, well‑supported manuscript that you can refine and submit.

### User Experience

**Paper writer.** Hydra assembles your research into a draft following common formats (e.g. IEEE, ACM or journal templates). It does this by adapting the staged drafting process from AutoResearchClaw: first summarising results, then constructing sections (Introduction, Related Work, Method, Experiments, Discussion), then refining language and verifying claims[5]. It checks each assertion against the sources and results in your knowledge base to prevent unsupported statements.

**Humanisation and polishing.** Before delivering a draft, Hydra applies humanisation and editing passes similar to your thesis assistant. It removes robotic phrasing, improves flow and ensures the draft meets IELTS writing criteria. It formats citations according to the chosen style and ensures figures and tables are referenced correctly.

**Templates and export.** You can choose from built‑in LaTeX or Markdown templates or provide your own. Hydra fills in the template, compiles it and shows a preview. You can edit sections in a WYSIWYG editor within the UI. When ready, export the paper as PDF, LaTeX or HTML. Hydra also prepares a reproducibility package with code, data, environment configuration and a README, following best practices for open science.

**Authorship ledger and ethics.** Hydra maintains a ledger of which parts were drafted by the AI versus written by you. This supports transparency and compliance with publication policies. Hydra never submits papers automatically; you review and approve the final version before export.

### User Interface

- **Manuscript editor.** The editor displays the draft broken into sections. Comments and tasks appear inline. You can request rewrites, insert citations or drag in figures and tables.
- **Citation manager.** A panel lists all citations used across your project. It flags duplicates, missing references and unused sources. You can search and edit entries.
- **Export and packaging.** When you approve the manuscript, choose export options. Hydra displays the PDF and package contents before saving. You can download or send them to collaborators.

### Under the Hood

Phase 4 borrows from the writing pipeline of AutoResearchClaw, but reimplements it as a Hydra-owned skill chain: a synthesiser gathers results, a structurer arranges them into sections, an editor polishes language and a verifier cross-checks claims[5]. Templates are stored locally and can be customised.

### Getting Started

1. **Finish a hypothesis cycle.** Once you have validated hypotheses and experiments, open the Manuscript page.
2. **Select a template.** Choose a journal or conference format or import your own.
3. **Generate draft.** Hydra compiles a first draft. Review, revise and request changes. Use the citation manager to ensure references are correct.
4. **Export.** When satisfied, export the paper and reproducibility package. Submit manually via the conference or journal’s system.

## Looking Ahead

Future phases of Hydra may integrate domain-specific simulators (e.g. chemical reaction modelling), automatic benchmark discovery, collaborative editing and knowledge sharing. Because Hydra owns a modular skill system inspired by proven agent tools, you can install or develop new skills easily. Each phase is designed to be **extensible and modular**: for example, you can plug in a different retrieval engine instead of PaperQA, or replace the Monte-Carlo search logic with another optimisation algorithm. Always remember that Hydra is a toolbox, not a wizard - its power comes from combining reliable open-source components into workflows that suit your research.

## References & Inspirations

- **Hermes Agent** – reference inspiration for skill-system and persistent-memory concepts[1]; Phase 1 does not require Hermes at runtime.
- **T3 Code** – reference inspiration for a minimal AI workspace interface; Hydra must not fork it or depend on it at runtime[2].
- **MLEvolve** – an autonomous algorithm‑search system using progressive Monte‑Carlo Graph Search and experience‑driven memory[7]; Hydra reuses and adapts its search logic for experiments.
- **AutoResearchClaw** – describes a 23‑stage pipeline with human‑in‑the‑loop modes and claim verification[5]; Hydra borrows its anti‑hallucination checks, staging and co‑pilot modes.
- **Co‑Scientist** – a multi‑agent hypothesis exploration system with Generation, Proximity, Reflection, Ranking and Evolution agents[9]; Hydra reimplements these roles and the idea tournament concept[11].
- **Colab FAQ** – warns that free Colab resources are not guaranteed and remote shells are disallowed[6]; Hydra respects these limits when offering free compute.
- **Hugging Face ZeroGPU** – provides free GPU minutes with quotas and an optional PRO tier[8]; Hydra uses it cautiously for quick demos.

[1] [3] [4] Hermes Agent Documentation | Hermes Agent

https://hermes-agent.nousresearch.com/docs/

[2] GitHub - pingdotgg/t3code · GitHub

https://github.com/pingdotgg/t3code

[5] GitHub - aiming-lab/AutoResearchClaw: Fully autonomous & self-evolving research from idea to paper. Chat an Idea. Get a Paper. · GitHub

https://github.com/aiming-lab/AutoResearchClaw

[6]  Google Colab 

https://research.google.com/colaboratory/faq.html

[7] GitHub - InternScience/MLEvolve: MLEvolve is an open-source autonomous system for end-to-end machine learning algorithm design and optimization powered by progressive search and experience-driven memory. · GitHub

https://github.com/InternScience/MLEvolve

[8] Spaces ZeroGPU: Dynamic GPU Allocation for Spaces · Hugging Face

https://huggingface.co/docs/hub/en/spaces-zerogpu

[9] [10] [11] Co-Scientist: A multi-agent AI partner to accelerate research — Google DeepMind

https://deepmind.google/blog/co-scientist-a-multi-agent-ai-partner-to-accelerate-research/
