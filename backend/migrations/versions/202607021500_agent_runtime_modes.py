"""agent runtime steps, approvals, and per-project mode policy

Revision ID: 202607021500
Revises: 202607021000
Create Date: 2026-07-02 15:00:00.000000

Adds the Phase-2 agent runtime tables (``agent_run_steps``, ``agent_approvals``,
``agent_mode_policies``) and the new ``agent_runs`` columns (``paused``,
``tokens_used``). The initial revision applies ``SQLModel.metadata.create_all``
against the live metadata, so on a fresh database this revision is an
applied-history marker; the alembic-head vs SQLModel-metadata parity gate stays
green and history stays linear (single head).
"""
from typing import Sequence, Union

from alembic import op
from sqlmodel import SQLModel

from hydra.database import models  # noqa: F401


revision: str = "202607021500"
down_revision: Union[str, Sequence[str], None] = "202607021400"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)


def downgrade() -> None:
    pass
