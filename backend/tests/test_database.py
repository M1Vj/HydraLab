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
    task = await crud.create_task(
        workspace_id=ws.id,
        title="Test Task",
        column_name="to_do",
        detail="Detail of task",
        progress=10,
        phase_indicator="retrieving sources",
        position=2
    )
    
    assert task.id is not None
    assert task.column_name == "to_do"
    assert task.progress == 10
    assert task.phase_indicator == "retrieving sources"
    assert task.position == 2
    
    updated = await crud.update_task(task.id, progress=50, column_name="in_progress", phase_indicator="summarising papers", position=1)
    assert updated.progress == 50
    assert updated.column_name == "in_progress"
    assert updated.phase_indicator == "summarising papers"
    assert updated.position == 1
    
    # Test Ordering
    task2 = await crud.create_task(
        workspace_id=ws.id,
        title="Second Task",
        column_name="to_do",
        detail="Another one",
        progress=0,
        phase_indicator="",
        position=0
    )
    
    tasks = await crud.get_tasks(ws.id)
    assert len(tasks) == 2
    # Since position 0 < 1, task2 should come first
    assert tasks[0].id == task2.id
    assert tasks[1].id == task.id

    # Test Deletion
    deleted = await crud.delete_task(task2.id)
    assert deleted is True
    
    tasks_after_delete = await crud.get_tasks(ws.id)
    assert len(tasks_after_delete) == 1
    assert tasks_after_delete[0].id == task.id
