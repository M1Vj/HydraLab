import uuid
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
from sqlmodel import SQLModel

sqlite_url = "sqlite+aiosqlite:///./hydra.db"

engine = create_async_engine(
    sqlite_url, echo=False, future=True, connect_args={"check_same_thread": False}
)

async_session_maker = sessionmaker(
    engine, class_=SQLModelAsyncSession, expire_on_commit=False
)

async def get_session() -> AsyncGenerator[SQLModelAsyncSession, None]:
    async with async_session_maker() as session:
        yield session

async def init_db():
    async with engine.begin() as conn:
        # run migrations in real life, but for basic tests we could just create
        # await conn.run_sync(SQLModel.metadata.create_all)
        pass
