from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import IngestionJob


class IngestionQueue:
    def __init__(self, session: AsyncSession, max_parallel_jobs: int = 2):
        self.session = session
        self.max_parallel_jobs = max_parallel_jobs

    async def enqueue(self, *, source_id: str, source_path: Path, priority: int = 0) -> IngestionJob:
        job = IngestionJob(source_id=source_id, source_path=str(source_path), priority=priority, status="queued")
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def pause(self, job_id: str) -> IngestionJob:
        return await self._update(job_id, status="paused")

    async def resume(self, job_id: str) -> IngestionJob:
        return await self._update(job_id, status="queued")

    async def retry(self, job_id: str) -> IngestionJob:
        job = await self._get(job_id)
        job.status = "queued"
        job.failure_reason = ""
        job.progress = 0
        job.retry_count += 1
        job.updated_at = _now()
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def cancel(self, job_id: str) -> IngestionJob:
        return await self._update(job_id, status="failed", failure_reason="cancelled")

    async def set_priority(self, job_id: str, priority: int) -> IngestionJob:
        job = await self._get(job_id)
        job.priority = priority
        job.updated_at = _now()
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def resume_after_restart(self) -> list[IngestionJob]:
        result = await self.session.exec(select(IngestionJob).where(IngestionJob.status == "running"))
        jobs = result.all()
        for job in jobs:
            job.status = "queued"
            job.updated_at = _now()
            self.session.add(job)
        await self.session.commit()
        return await self.pending_jobs()

    async def pending_jobs(self) -> list[IngestionJob]:
        result = await self.session.exec(
            select(IngestionJob)
            .where(IngestionJob.status == "queued")
            .order_by(IngestionJob.priority.desc(), IngestionJob.created_at.asc())
        )
        return list(result.all())

    async def _update(self, job_id: str, **fields: object) -> IngestionJob:
        job = await self._get(job_id)
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = _now()
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def _get(self, job_id: str) -> IngestionJob:
        job = await self.session.get(IngestionJob, job_id)
        if job is None:
            raise KeyError(f"ingestion job not found: {job_id}")
        return job


def _now() -> datetime:
    return datetime.now(timezone.utc)
