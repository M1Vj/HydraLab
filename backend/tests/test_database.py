import pytest
import pytest_asyncio
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

from hydra.database.models import Workspace, Conversation, Task
from hydra.database.crud import CRUD

@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def session(engine):
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_maker() as session:
        yield session

@pytest.mark.asyncio
async def test_crud_workspace(session: AsyncSession):
    crud = CRUD(session)
    ws = await crud.create_workspace("Test Workspace")
    assert ws.id is not None
    assert ws.name == "Test Workspace"

    fetched = await crud.get_workspace(ws.id)
    assert fetched is not None
    assert fetched.name == "Test Workspace"

    workspaces = await crud.get_workspaces()
    assert len(workspaces) == 1

@pytest.mark.asyncio
async def test_crud_conversation(session: AsyncSession):
    crud = CRUD(session)
    ws = await crud.create_workspace("WS for Conv")
    conv = await crud.create_conversation(ws.id, "Test Conv")
    
    assert conv.id is not None
    assert conv.workspace_id == ws.id
    
    convs = await crud.get_conversations(ws.id)
    assert len(convs) == 1
    assert convs[0].title == "Test Conv"

@pytest.mark.asyncio
async def test_crud_task(session: AsyncSession):
    crud = CRUD(session)
    ws = await crud.create_workspace("WS for Task")
    task = await crud.create_task(ws.id, "Test Task", "To Do", "Detail of task")
    
    assert task.id is not None
    assert task.column_name == "To Do"
    
    updated = await crud.update_task(task.id, progress=50, column_name="In Progress")
    assert updated.progress == 50
    assert updated.column_name == "In Progress"
    
    tasks = await crud.get_tasks(ws.id)
    assert len(tasks) == 1
    assert tasks[0].progress == 50
