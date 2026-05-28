import React, { FormEvent, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BookOpenCheck,
  CheckCircle2,
  FileText,
  Library,
  ListTodo,
  MessageSquareText,
  Search,
  Send,
  Settings,
  Sparkles,
} from "lucide-react";

import { apiJson, groupTasksByColumn, sourceLabel, statusCopy, Source, Task } from "./lib/hydra";
import "./styles.css";

type ResearchResponse = {
  answer: string;
  status: string;
  citations: Array<{ id: string; source_id: string; claim: string; quote: string }>;
  sources: Source[];
};

type Note = {
  id: string;
  title: string;
  body: string;
  source_id?: string;
};

type EventItem = {
  id: string;
  kind: string;
  message: string;
  created_at: number;
};

function App() {
  const [query, setQuery] = useState("retrieval augmented generation for scientific papers");
  const [answer, setAnswer] = useState<ResearchResponse | null>(null);
  const [draft, setDraft] = useState("This proves the method is always best. It is very good.");
  const [review, setReview] = useState<{ rewrite: string; critique: string[]; unsupported_claims: string[] } | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [bibliography, setBibliography] = useState("");
  const [busy, setBusy] = useState(false);

  const groupedTasks = useMemo(() => groupTasksByColumn(tasks), [tasks]);

  useEffect(() => {
    void refreshWorkspace();
  }, []);

  async function refreshWorkspace() {
    const [noteData, taskData, eventData] = await Promise.all([
      apiJson<{ notes: Note[] }>("/api/notes").catch(() => ({ notes: [] })),
      apiJson<{ tasks: Task[] }>("/api/tasks").catch(() => ({ tasks: [] })),
      apiJson<{ events: EventItem[] }>("/api/events").catch(() => ({ events: [] })),
    ]);
    setNotes(noteData.notes);
    setTasks(taskData.tasks);
    setEvents(eventData.events);
  }

  async function submitResearch(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const payload = await apiJson<ResearchResponse>("/api/chat/research", {
        method: "POST",
        body: JSON.stringify({ query }),
      });
      setAnswer(payload);
      setSources(payload.sources);
      await refreshWorkspace();
    } finally {
      setBusy(false);
    }
  }

  async function uploadPaper(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    const body = new FormData();
    body.append("file", file);
    const response = await fetch("/api/papers/ingest", { method: "POST", body });
    if (!response.ok) {
      throw new Error(`Hydra API error ${response.status}`);
    }
    const payload = (await response.json()) as { source: Source };
    setSources((current) => [payload.source, ...current]);
    await refreshWorkspace();
  }

  async function loadBibliography(style: "apa" | "bibtex") {
    const response = await fetch(`/api/export/bibliography?style=${style}`);
    if (!response.ok) {
      throw new Error(`Hydra API error ${response.status}`);
    }
    setBibliography(await response.text());
  }

  async function submitReview() {
    const payload = await apiJson<{ rewrite: string; critique: string[]; unsupported_claims: string[] }>(
      "/api/writing/review",
      { method: "POST", body: JSON.stringify({ text: draft }) },
    );
    setReview(payload);
    await refreshWorkspace();
  }

  async function createTask() {
    const task = await apiJson<Task>("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ title: `Review sources ${tasks.length + 1}`, column: "To Do" }),
    });
    setTasks((current) => [...current, task]);
    await refreshWorkspace();
  }

  async function moveTask(task: Task, column: string) {
    const moved = await apiJson<Task>(`/api/tasks/${task.id}`, {
      method: "PATCH",
      body: JSON.stringify({ column, progress: column === "Done" ? 100 : task.progress }),
    });
    setTasks((current) => current.map((item) => (item.id === moved.id ? moved : item)));
    await refreshWorkspace();
  }

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Hydra navigation">
        <div className="brand-mark">
          <Sparkles aria-hidden="true" />
          <div>
            <strong>Hydra</strong>
            <span>Research companion</span>
          </div>
        </div>
        <nav>
          <a href="#research"><MessageSquareText aria-hidden="true" /> Research</a>
          <a href="#sources"><Library aria-hidden="true" /> Sources</a>
          <a href="#notes"><FileText aria-hidden="true" /> Notes</a>
          <a href="#tasks"><ListTodo aria-hidden="true" /> Tasks</a>
          <a href="#settings"><Settings aria-hidden="true" /> Settings</a>
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p>Phase 1</p>
            <h1>Research desk</h1>
          </div>
          <div className="status-pill">
            <CheckCircle2 aria-hidden="true" />
            Read-only tools
          </div>
        </header>

        <section className="research-grid" id="research">
          <article className="chat-panel">
            <form onSubmit={submitResearch} className="search-box">
              <Search aria-hidden="true" />
              <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Research question" />
              <button type="submit" disabled={busy} title="Send research question">
                <Send aria-hidden="true" />
              </button>
            </form>

            <div className="answer-surface">
              {answer ? (
                <>
                  <div className="answer-status">{statusCopy(answer.status)}</div>
                  <p>{answer.answer}</p>
                  <div className="citation-list">
                    {answer.sources.map((source) => (
                      <a key={source.id} href={source.url || "#"}>{sourceLabel(source)}</a>
                    ))}
                  </div>
                </>
              ) : (
                <p className="empty-state">Ask Hydra to search literature, summarize evidence, and return citations.</p>
              )}
            </div>
          </article>

          <article className="writing-panel">
            <h2>Writing review</h2>
            <textarea value={draft} onChange={(event) => setDraft(event.target.value)} aria-label="Draft text" />
            <button onClick={submitReview}>Review draft</button>
            {review ? (
              <div className="review-output">
                <strong>Rewrite</strong>
                <p>{review.rewrite}</p>
                <strong>Critique</strong>
                <ul>{review.critique.map((item) => <li key={item}>{item}</li>)}</ul>
              </div>
            ) : null}
          </article>
        </section>

        <section className="lower-grid">
          <article id="sources">
            <h2><Library aria-hidden="true" /> Sources</h2>
            <label className="upload-control">
              Upload paper
              <input type="file" accept=".pdf,.txt,.md,text/plain,application/pdf" onChange={(event) => void uploadPaper(event)} />
            </label>
            {(sources.length ? sources : answer?.sources ?? []).map((source) => (
              <div className="note-row" key={source.id ?? source.title}>
                <strong>{sourceLabel(source)}</strong>
                <p>{source.abstract || source.url || "Local source"}</p>
              </div>
            ))}
            {!sources.length && !answer?.sources.length ? <p className="empty-state">Search or upload papers to build source trace.</p> : null}
          </article>

          <article id="notes">
            <h2><BookOpenCheck aria-hidden="true" /> Notes</h2>
            {notes.length === 0 ? <p className="empty-state">Notes from papers and drafts appear here.</p> : null}
            {notes.map((note) => (
              <div className="note-row" key={note.id}>
                <strong>{note.title}</strong>
                <p>{note.body}</p>
              </div>
            ))}
          </article>

          <article id="tasks">
            <div className="panel-title">
              <h2><ListTodo aria-hidden="true" /> Kanban</h2>
              <button onClick={createTask}>Add task</button>
            </div>
            <div className="kanban-board">
              {groupedTasks.map((column) => (
                <div className="kanban-column" key={column.name}>
                  <h3>{column.name}</h3>
                  {column.tasks.map((task) => (
                    <div className="task-card" key={task.id}>
                      <strong>{task.title}</strong>
                      <progress value={task.progress} max={100} />
                      <select value={task.column} onChange={(event) => void moveTask(task, event.target.value)} aria-label={`Move ${task.title}`}>
                        {groupedTasks.map((target) => <option key={target.name}>{target.name}</option>)}
                      </select>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </article>

          <article className="activity-panel">
            <h2>Status trace</h2>
            {events.slice(0, 8).map((event) => (
              <div className="event-row" key={event.id}>
                <span>{event.kind}</span>
                <p>{event.message}</p>
              </div>
            ))}
          </article>

          <article id="settings" className="settings-panel">
            <h2><Settings aria-hidden="true" /> Settings & export</h2>
            <p>Provider-neutral Phase 1 setup. Add local keys through environment or future secure settings storage; no external mutations run from this UI.</p>
            <div className="export-actions">
              <button onClick={() => void loadBibliography("apa")}>APA export</button>
              <button onClick={() => void loadBibliography("bibtex")}>BibTeX export</button>
            </div>
            {bibliography ? <pre>{bibliography}</pre> : null}
          </article>
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
