from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator
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


def get_engine():
    db_url = get_db_url()
    if db_url not in _engines:
        engine = create_async_engine(
            db_url, echo=False, future=True, connect_args={"check_same_thread": False}
        )
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


async def init_db():
    db_url = get_db_url()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    _initialized_databases.add(db_url)


async def get_session() -> AsyncGenerator[SQLModelAsyncSession, None]:
    db_url = get_db_url()
    if db_url not in _initialized_databases:
        await init_db()
    
    maker = get_session_maker()
    async with maker() as session:
        yield session
