"""experiment execution & compute

Revision ID: 202607030600
Revises: 202607030500
Create Date: 2026-07-03 06:00:00.000000

Adds the Phase-3 gated compute subsystem tables (compute_backends,
experiment_runs, experiment_run_logs, experiment_execution_settings) via the
SQLModel create_all marker pattern, keeping the Alembic history linear with a
single head.
"""
from typing import Sequence, Union

from alembic import op
from sqlmodel import SQLModel

from hydra.database import models  # noqa: F401 - registers the new tables

revision: str = "202607030600"
down_revision: Union[str, Sequence[str], None] = "202607030500"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)


def downgrade() -> None:
    for table in (
        "experiment_run_logs",
        "experiment_runs",
        "experiment_execution_settings",
        "compute_backends",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
