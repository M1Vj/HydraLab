"""Background drain for the ingestion queue.

The queue (``IngestionQueue``) persists jobs; this worker turns queued jobs
into completed conversions by handing each one to ``IngestionService``. It runs
as a single serial loop off the app lifespan so a slow conversion never blocks
an HTTP request, while job status/progress stay observable in the database.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import Source
from hydra.services.ingestion.queue import IngestionQueue
from hydra.services.ingestion.service import IngestionService

IDLE_POLL_SECONDS = 1.0


async def process_next_job(
    session: AsyncSession,
    *,
    project_root: Path,
    service: Optional[IngestionService] = None,
) -> Optional[dict[str, Any]]:
    """Process the highest-priority queued job to completion.

    Returns the ingestion result, or None when the queue is empty. Status
    transitions (running/done/failed/quarantined) are owned by IngestionService,
    which is handed the persisted job row so its progress is visible throughout.
    """
    queue = IngestionQueue(session)
    pending = await queue.pending_jobs()
    if not pending:
        return None
    job = pending[0]
    source = await session.get(Source, job.source_id) if job.source_id else None
    service = service or IngestionService()
    return await service.ingest(
        session,
        source_id=job.source_id or "",
        title=source.title if source else "Ingestion",
        source_path=Path(job.source_path),
        project_root=project_root,
        job=job,
    )


async def run_ingestion_worker(
    session_factory: Callable[[], Any],
    *,
    project_root: Path,
    idle_seconds: float = IDLE_POLL_SECONDS,
) -> None:
    """Continuously drain the ingestion queue until cancelled.

    Each job runs in its own session so a failure never poisons a shared unit of
    work. A crash in one job is swallowed (the job is already marked failed by
    the service) so the loop keeps serving the rest of the queue.
    """
    while True:
        processed = False
        try:
            async with session_factory() as session:
                result = await process_next_job(session, project_root=project_root)
                processed = result is not None
        except asyncio.CancelledError:
            raise
        except Exception:  # keep the loop alive; the job row records its own failure
            processed = False
        await asyncio.sleep(0 if processed else idle_seconds)
