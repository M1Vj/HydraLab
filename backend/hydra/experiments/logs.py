"""Bounded per-run log/metric persistence (HL-SAFE-14).

Stdout/stderr and metric events are persisted keyed by ``run_id`` with a hard
byte cap. When the cap is reached the stored content keeps the first N bytes and
appends the literal marker ``[truncated: <omitted> bytes omitted]`` — data is
never silently dropped, and every persisted row carries its ``run_id``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from hydra.database.models import ExperimentRunLog

DEFAULT_LOG_CAP_BYTES = 1024 * 1024


@dataclass
class TruncationOutcome:
    content: str
    byte_len: int
    truncated: bool
    omitted: int


def apply_cap(text: str, cap_bytes: int) -> TruncationOutcome:
    """Return the capped content plus an explicit truncation marker if needed."""
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= cap_bytes:
        return TruncationOutcome(content=text, byte_len=len(raw), truncated=False, omitted=0)
    omitted = len(raw) - cap_bytes
    head = raw[:cap_bytes].decode("utf-8", errors="ignore")
    marker = f"[truncated: {omitted} bytes omitted]"
    content = head + marker
    return TruncationOutcome(
        content=content,
        byte_len=len(content.encode("utf-8", errors="replace")),
        truncated=True,
        omitted=omitted,
    )


class RunLogStore:
    def __init__(self, session: AsyncSession, *, cap_bytes: int = DEFAULT_LOG_CAP_BYTES) -> None:
        self.session = session
        self.cap_bytes = cap_bytes

    async def _next_seq(self, run_id: str) -> int:
        res = await self.session.exec(
            select(ExperimentRunLog).where(ExperimentRunLog.run_id == run_id)
        )
        return len(list(res.all()))

    async def append_stream(self, run_id: str, stream: str, text: str) -> ExperimentRunLog:
        outcome = apply_cap(text, self.cap_bytes)
        row = ExperimentRunLog(
            run_id=run_id,
            stream=stream,
            seq=await self._next_seq(run_id),
            content=outcome.content,
            byte_len=outcome.byte_len,
            truncated=outcome.truncated,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def record_metrics(self, run_id: str, metrics: dict) -> ExperimentRunLog:
        payload = json.dumps(metrics, sort_keys=True)
        row = ExperimentRunLog(
            run_id=run_id,
            stream="metric",
            seq=await self._next_seq(run_id),
            content=payload,
            byte_len=len(payload.encode("utf-8", errors="replace")),
            truncated=False,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def read(self, run_id: str) -> list[ExperimentRunLog]:
        res = await self.session.exec(
            select(ExperimentRunLog)
            .where(ExperimentRunLog.run_id == run_id)
            .order_by(ExperimentRunLog.seq.asc())
        )
        return list(res.all())
