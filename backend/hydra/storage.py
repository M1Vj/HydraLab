from __future__ import annotations

import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


def hydra_home() -> Path:
    return Path(os.environ.get("HYDRA_HOME", Path.cwd() / ".hydra")).expanduser()


class Store:
    def __init__(self, db_path: Path | None = None) -> None:
        self.home = hydra_home()
        self.home.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path or self.home / "hydra.db"
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
              id TEXT PRIMARY KEY,
              conversation_id TEXT NOT NULL REFERENCES conversations(id),
              role TEXT NOT NULL,
              content TEXT NOT NULL,
              created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sources (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              authors TEXT NOT NULL DEFAULT '',
              year TEXT NOT NULL DEFAULT '',
              url TEXT NOT NULL DEFAULT '',
              abstract TEXT NOT NULL DEFAULT '',
              kind TEXT NOT NULL DEFAULT 'article',
              created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS citations (
              id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL REFERENCES sources(id),
              text TEXT NOT NULL,
              created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS claims (
              id TEXT PRIMARY KEY,
              text TEXT NOT NULL,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence_links (
              id TEXT PRIMARY KEY,
              claim_id TEXT NOT NULL REFERENCES claims(id),
              citation_id TEXT REFERENCES citations(id),
              source_id TEXT NOT NULL REFERENCES sources(id),
              passage TEXT NOT NULL,
              support TEXT NOT NULL,
              confidence REAL NOT NULL,
              review_status TEXT NOT NULL,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notes (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              body TEXT NOT NULL,
              source_id TEXT REFERENCES sources(id),
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(id UNINDEXED, title, body);
            CREATE TABLE IF NOT EXISTS tasks (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              detail TEXT NOT NULL DEFAULT '',
              column_name TEXT NOT NULL,
              progress INTEGER NOT NULL DEFAULT 0,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activity_events (
              id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              message TEXT NOT NULL,
              payload TEXT NOT NULL DEFAULT '{}',
              created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provider_settings (
              id TEXT PRIMARY KEY,
              provider TEXT NOT NULL,
              model TEXT NOT NULL,
              api_key_ref TEXT NOT NULL DEFAULT '',
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def add_event(self, kind: str, message: str, payload: str = "{}") -> dict[str, Any]:
        row = {"id": new_id("evt"), "kind": kind, "message": message, "payload": payload, "created_at": time.time()}
        self.conn.execute(
            "INSERT INTO activity_events (id, kind, message, payload, created_at) VALUES (:id, :kind, :message, :payload, :created_at)",
            row,
        )
        self.conn.commit()
        return row

    def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM activity_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def create_conversation(self, title: str) -> dict[str, Any]:
        row = {"id": new_id("conv"), "title": title, "created_at": time.time()}
        self.conn.execute(
            "INSERT INTO conversations (id, title, created_at) VALUES (:id, :title, :created_at)",
            row,
        )
        self.conn.commit()
        return row

    def list_conversations(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM conversations ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def add_message(self, conversation_id: str, role: str, content: str) -> dict[str, Any]:
        row = {
            "id": new_id("msg"),
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "created_at": time.time()
        }
        self.conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (:id, :conversation_id, :role, :content, :created_at)",
            row,
        )
        self.conn.commit()
        return row

    def list_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def upsert_source(self, source: dict[str, Any]) -> dict[str, Any]:
        source = {
            "id": source.get("id") or new_id("src"),
            "title": source.get("title") or "Untitled source",
            "authors": source.get("authors") or "",
            "year": str(source.get("year") or ""),
            "url": source.get("url") or "",
            "abstract": source.get("abstract") or "",
            "kind": source.get("kind") or "article",
            "created_at": source.get("created_at") or time.time(),
        }
        self.conn.execute(
            """
            INSERT OR REPLACE INTO sources (id, title, authors, year, url, abstract, kind, created_at)
            VALUES (:id, :title, :authors, :year, :url, :abstract, :kind, :created_at)
            """,
            source,
        )
        self.conn.commit()
        return source

    def list_sources(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM sources ORDER BY created_at DESC").fetchall()]

    def add_citation(self, source_id: str, text: str) -> dict[str, Any]:
        row = {"id": new_id("cit"), "source_id": source_id, "text": text, "created_at": time.time()}
        self.conn.execute(
            "INSERT INTO citations (id, source_id, text, created_at) VALUES (:id, :source_id, :text, :created_at)",
            row,
        )
        self.conn.commit()
        return row

    def list_citations(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM citations ORDER BY created_at DESC").fetchall()]

    def add_claim(self, text: str) -> dict[str, Any]:
        now = time.time()
        row = {"id": new_id("clm"), "text": text, "created_at": now, "updated_at": now}
        self.conn.execute(
            "INSERT INTO claims (id, text, created_at, updated_at) VALUES (:id, :text, :created_at, :updated_at)",
            row,
        )
        self.conn.commit()
        return row

    def list_claims(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM claims ORDER BY created_at DESC").fetchall()]

    def add_evidence(
        self,
        claim_id: str,
        source_id: str,
        passage: str,
        support: str,
        confidence: float,
        review_status: str = "needs_review",
        citation_id: str | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        row = {
            "id": new_id("evd"),
            "claim_id": claim_id,
            "citation_id": citation_id,
            "source_id": source_id,
            "passage": passage,
            "support": support,
            "confidence": confidence,
            "review_status": review_status,
            "created_at": now,
            "updated_at": now,
        }
        self.conn.execute(
            """
            INSERT INTO evidence_links
              (id, claim_id, citation_id, source_id, passage, support, confidence, review_status, created_at, updated_at)
            VALUES
              (:id, :claim_id, :citation_id, :source_id, :passage, :support, :confidence, :review_status, :created_at, :updated_at)
            """,
            row,
        )
        self.conn.commit()
        return row

    def list_evidence(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT evidence_links.*, sources.title AS source_title, sources.url AS source_url, claims.text AS claim_text
            FROM evidence_links
            JOIN sources ON sources.id = evidence_links.source_id
            JOIN claims ON claims.id = evidence_links.claim_id
            ORDER BY evidence_links.created_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def add_note(self, title: str, body: str, source_id: str | None = None) -> dict[str, Any]:
        now = time.time()
        row = {"id": new_id("note"), "title": title, "body": body, "source_id": source_id, "created_at": now, "updated_at": now}
        self.conn.execute(
            "INSERT INTO notes (id, title, body, source_id, created_at, updated_at) VALUES (:id, :title, :body, :source_id, :created_at, :updated_at)",
            row,
        )
        self.conn.execute("INSERT INTO notes_fts (id, title, body) VALUES (?, ?, ?)", (row["id"], title, body))
        self.conn.commit()
        return row

    def search_notes(self, query: str | None = None) -> list[dict[str, Any]]:
        if query:
            rows = self.conn.execute(
                """
                SELECT notes.* FROM notes_fts
                JOIN notes ON notes.id = notes_fts.id
                WHERE notes_fts MATCH ?
                ORDER BY notes.updated_at DESC
                """,
                (query,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM notes ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def add_task(self, title: str, column: str, detail: str = "") -> dict[str, Any]:
        now = time.time()
        row = {"id": new_id("task"), "title": title, "detail": detail, "column": column, "progress": 0, "created_at": now, "updated_at": now}
        self.conn.execute(
            "INSERT INTO tasks (id, title, detail, column_name, progress, created_at, updated_at) VALUES (:id, :title, :detail, :column, :progress, :created_at, :updated_at)",
            row,
        )
        self.conn.commit()
        return row

    def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        current = self.conn.execute("SELECT id, title, detail, column_name AS column, progress, created_at, updated_at FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if current is None:
            return None
        row = dict(current)
        for key in ("title", "detail", "column", "progress"):
            if updates.get(key) is not None:
                row[key] = updates[key]
        row["updated_at"] = time.time()
        self.conn.execute(
            "UPDATE tasks SET title = :title, detail = :detail, column_name = :column, progress = :progress, updated_at = :updated_at WHERE id = :id",
            row,
        )
        self.conn.commit()
        return row

    def list_tasks(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT id, title, detail, column_name AS column, progress, created_at, updated_at FROM tasks ORDER BY created_at").fetchall()
        return [dict(row) for row in rows]

    def save_provider_settings(self, provider: str, model: str, api_key_ref: str = "") -> dict[str, Any]:
        now = time.time()
        existing = self.conn.execute(
            "SELECT id, created_at FROM provider_settings WHERE provider = ?",
            (provider,),
        ).fetchone()
        row = {
            "id": existing["id"] if existing else new_id("set"),
            "provider": provider,
            "model": model,
            "api_key_ref": api_key_ref,
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
        }
        self.conn.execute(
            """
            INSERT INTO provider_settings (id, provider, model, api_key_ref, created_at, updated_at)
            VALUES (:id, :provider, :model, :api_key_ref, :created_at, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
              model = excluded.model,
              api_key_ref = excluded.api_key_ref,
              updated_at = excluded.updated_at
            """,
            row,
        )
        self.conn.commit()
        return row

    def list_provider_settings(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, provider, model, api_key_ref, created_at, updated_at FROM provider_settings ORDER BY provider"
        ).fetchall()
        return [dict(row) for row in rows]

    def export_workspace(self) -> dict[str, Any]:
        return {
            "sources": self.list_sources(),
            "notes": self.search_notes(),
            "tasks": self.list_tasks(),
            "events": self.list_events(),
            "evidence": self.list_evidence(),
            "provider_settings": self.list_provider_settings(),
        }


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
