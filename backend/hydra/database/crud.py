from typing import List, Optional
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from hydra.database.models import Workspace, Conversation, Message, Task

class CRUD:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_workspace(self, name: str) -> Workspace:
        workspace = Workspace(name=name)
        self.session.add(workspace)
        await self.session.commit()
        await self.session.refresh(workspace)
        return workspace

    async def get_workspaces(self) -> List[Workspace]:
        result = await self.session.exec(select(Workspace))
        return result.all()

    async def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        result = await self.session.exec(select(Workspace).where(Workspace.id == workspace_id))
        return result.first()

    async def create_conversation(self, workspace_id: str, title: str) -> Conversation:
        conv = Conversation(workspace_id=workspace_id, title=title)
        self.session.add(conv)
        await self.session.commit()
        await self.session.refresh(conv)
        return conv

    async def get_conversations(self, workspace_id: str) -> List[Conversation]:
        result = await self.session.exec(select(Conversation).where(Conversation.workspace_id == workspace_id))
        return result.all()

    async def create_task(self, workspace_id: str, title: str, column_name: str, detail: str, progress: int = 0, phase_indicator: str = "", position: int = 0) -> Task:
        task = Task(workspace_id=workspace_id, title=title, column_name=column_name, detail=detail, progress=progress, phase_indicator=phase_indicator, position=position)
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def get_tasks(self, workspace_id: str) -> List[Task]:
        result = await self.session.exec(
            select(Task)
            .where(Task.workspace_id == workspace_id)
            .order_by(Task.position.asc(), Task.created_at.asc())
        )
        return result.all()

    async def update_task(self, task_id: str, **kwargs) -> Optional[Task]:
        result = await self.session.exec(select(Task).where(Task.id == task_id))
        task = result.first()
        if not task:
            return None
        for k, v in kwargs.items():
            setattr(task, k, v)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def delete_task(self, task_id: str) -> bool:
        result = await self.session.exec(select(Task).where(Task.id == task_id))
        task = result.first()
        if not task:
            return False
        await self.session.delete(task)
        await self.session.commit()
        return True
