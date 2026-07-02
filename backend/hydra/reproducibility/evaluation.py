"""Evaluation-result persistence (HL-QUAL-32)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import EvaluationResult


def _coerce_dt(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def record_evaluation_result(
    session: AsyncSession,
    *,
    run_id: str,
    metric_name: str,
    value: float,
    evaluated_artifact_hash: str,
    created_at: datetime | str | None = None,
) -> EvaluationResult:
    row = EvaluationResult(
        run_id=run_id,
        metric_name=metric_name,
        value=float(value),
        evaluated_artifact_hash=evaluated_artifact_hash,
        created_at=_coerce_dt(created_at),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_evaluation_results(session: AsyncSession, run_id: str) -> list[EvaluationResult]:
    result = await session.exec(
        select(EvaluationResult).where(EvaluationResult.run_id == run_id).order_by(EvaluationResult.created_at.asc())
    )
    return list(result.all())
