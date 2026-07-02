from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
from sqlmodel import SQLModel

_engines = {}
_session_makers = {}
_initialized_databases = set()


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def get_db_url() -> str:
    home = Path(os.environ.get("HYDRA_HOME", _project_root() / ".hydra")).expanduser()
    home.mkdir(parents=True, exist_ok=True)
    db_path = home / "hydra.db"
    return f"sqlite+aiosqlite:///{db_path}"


def _install_sqlite_pragmas(engine) -> None:
    """Enforce per-connection SQLite pragmas the ORM does not set by default.

    ``journal_mode=WAL`` lets a reader and the single writer coexist instead of
    blocking; ``busy_timeout`` waits on a briefly-locked DB instead of raising
    ``database is locked`` immediately.

    NOTE: ``PRAGMA foreign_keys=ON`` is intentionally NOT set here yet. Turning it
    on surfaces pre-existing referential-integrity violations in currently-working
    flows (quarantine ingestion jobs carry a synthetic ``quarantine:`` source_id
    with no ``sources`` row; project restore inserts notes before recreating their
    parent project/workspace). Enabling enforcement is a dedicated data-layer task
    that must fix those flows (nullable/real source refs, parent-row ordering)
    with regression tests — shipping it half-done would break real features.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # pragma: no cover - driver callback
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()


def get_engine():
    db_url = get_db_url()
    if db_url not in _engines:
        engine = create_async_engine(
            db_url, echo=False, future=True, connect_args={"check_same_thread": False}
        )
        _install_sqlite_pragmas(engine)
        _engines[db_url] = engine
    return _engines[db_url]


def get_session_maker():
    db_url = get_db_url()
    if db_url not in _session_makers:
        engine = get_engine()
        maker = sessionmaker(
            engine, class_=SQLModelAsyncSession, expire_on_commit=False
        )
        _session_makers[db_url] = maker
    return _session_makers[db_url]


class SessionMakerProxy:
    def __call__(self):
        return get_session_maker()()


async_session_maker = SessionMakerProxy()


def _install_append_only_triggers(sync_conn) -> None:
    """Install the append-only ledger triggers on the real app DB.

    The forensic ledgers (agent audit, collaborative-edit audit) rely on SQLite
    triggers that ABORT any UPDATE/DELETE. Tests install these via fixtures, but
    ``create_all`` never emits them — so without this the defense-in-depth was
    absent in the shipped database. ``CREATE TRIGGER IF NOT EXISTS`` is idempotent.
    """
    from hydra.autonomy.audit import LEDGER_APPEND_ONLY_TRIGGERS
    from hydra.collaboration.audit import COLLABORATION_AUDIT_APPEND_ONLY_TRIGGERS

    for statement in (*LEDGER_APPEND_ONLY_TRIGGERS, *COLLABORATION_AUDIT_APPEND_ONLY_TRIGGERS):
        sync_conn.exec_driver_sql(statement)


def _stamp_alembic_head(sync_conn) -> None:
    """Record the alembic head on a freshly ``create_all``-provisioned DB.

    A create_all schema already matches head; stamping prevents a later
    ``alembic upgrade`` from replaying migrations that would collide with the
    existing tables. Best-effort: a missing/unreadable alembic config must never
    block first-run startup, and an already-stamped DB is left untouched.
    """
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        ini = _project_root() / "backend" / "alembic.ini"
        if not ini.exists():
            return
        heads = ScriptDirectory.from_config(Config(str(ini))).get_heads()
        if not heads:
            return
        sync_conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
        already = sync_conn.exec_driver_sql("SELECT 1 FROM alembic_version LIMIT 1").fetchone()
        if already:
            return
        for head in heads:
            sync_conn.exec_driver_sql(
                "INSERT INTO alembic_version (version_num) VALUES (?)", (head,)
            )
    except Exception:
        # Startup must survive a missing alembic toolchain / config.
        return


async def init_db():
    db_url = get_db_url()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        await conn.run_sync(_install_append_only_triggers)
        await conn.run_sync(_stamp_alembic_head)
    _initialized_databases.add(db_url)


async def get_session() -> AsyncGenerator[SQLModelAsyncSession, None]:
    db_url = get_db_url()
    if db_url not in _initialized_databases:
        await init_db()
    
    maker = get_session_maker()
    async with maker() as session:
        yield session
