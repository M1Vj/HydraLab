from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import and_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import BrowserActionLog, BrowserHostPermission


HOST_PERMISSION_STATES = ("ask", "allow_for_task", "always_allow_host", "blocked")
ACTION_LOG_IMMUTABLE_MESSAGE = "browser action log rows are append-only"


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class BrowserHostPermissionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, project_id: str, host: str, task_group_id: str | None = None) -> dict[str, Any]:
        clean_host = (host or "").lower()
        query = select(BrowserHostPermission).where(
            and_(BrowserHostPermission.project_id == project_id, BrowserHostPermission.host == clean_host)
        )
        row = (await self.session.exec(query)).first()
        if row is None:
            return {"id": None, "project_id": project_id, "host": clean_host, "state": "ask", "task_group_id": None}
        result = self._to_dict(row)
        # "allow_for_task" is scoped to the task group it was granted for. When a
        # task group is supplied and does not match the one the grant is bound to,
        # downgrade to "ask" so a different task (or a redirect landing under
        # another task) must re-request approval. A grant with no bound group
        # (task_group_id is None) is honored for NO specific task and downgrades
        # too, so it can never leak across task groups. "always_allow_host" stays
        # project-wide (03-06).
        if (
            task_group_id is not None
            and result["state"] == "allow_for_task"
            and result["task_group_id"] != task_group_id
        ):
            result = {**result, "state": "ask"}
        return result

    async def set(
        self,
        project_id: str,
        host: str,
        state: str,
        *,
        task_group_id: str | None = None,
    ) -> dict[str, Any]:
        if state not in HOST_PERMISSION_STATES:
            raise ValueError(f"invalid browser host permission state: {state}")
        if state == "allow_for_task" and not task_group_id:
            raise ValueError("allow_for_task requires a task_group_id")
        clean_host = (host or "").lower()
        query = select(BrowserHostPermission).where(
            and_(BrowserHostPermission.project_id == project_id, BrowserHostPermission.host == clean_host)
        )
        row = (await self.session.exec(query)).first()
        if row is None:
            row = BrowserHostPermission(project_id=project_id, host=clean_host)
        row.state = state
        row.task_group_id = task_group_id
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return self._to_dict(row)

    def _to_dict(self, row: BrowserHostPermission) -> dict[str, Any]:
        return {
            "id": row.id,
            "project_id": row.project_id,
            "host": row.host,
            "state": row.state,
            "task_group_id": row.task_group_id,
            "updated_at": _iso(row.updated_at),
        }


class BrowserActionLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def append(
        self,
        *,
        project_id: str,
        action: str,
        host: str,
        mode: str,
        approval_result: str,
        target_url: str = "",
        task_group_id: str | None = None,
        trust_level: str = "user-curated",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = BrowserActionLog(
            project_id=project_id,
            action=action,
            host=(host or "").lower(),
            mode=mode,
            approval_result=approval_result,
            target_url=target_url,
            task_group_id=task_group_id,
            trust_level=trust_level,
            payload_json=json.dumps(payload or {}, sort_keys=True),
            timestamp=datetime.now(timezone.utc),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return self._to_dict(row)

    async def list(self, project_id: str | None = None) -> list[dict[str, Any]]:
        query = select(BrowserActionLog)
        if project_id:
            query = query.where(BrowserActionLog.project_id == project_id)
        query = query.order_by(BrowserActionLog.timestamp.asc())
        rows = (await self.session.exec(query)).all()
        return [self._to_dict(row) for row in rows]

    async def update(self, log_id: str, **_: Any) -> None:
        raise PermissionError(ACTION_LOG_IMMUTABLE_MESSAGE)

    def _to_dict(self, row: BrowserActionLog) -> dict[str, Any]:
        return {
            "id": row.id,
            "project_id": row.project_id,
            "action": row.action,
            "host": row.host,
            "mode": row.mode,
            "approval_result": row.approval_result,
            "target_url": row.target_url,
            "task_group_id": row.task_group_id,
            "trust_level": row.trust_level,
            "payload": json.loads(row.payload_json or "{}"),
            "timestamp": _iso(row.timestamp),
        }
