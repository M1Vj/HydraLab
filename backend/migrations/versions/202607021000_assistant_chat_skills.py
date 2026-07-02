"""assistant chat skills context memory

Revision ID: 202607021000
Revises: 202607021130 (re-chained at merge; authored off pre-parallel head)
Create Date: 2026-07-02 10:00:00.000000

Adds the ``context_file_changes`` table and the assistant/chat/provider metadata
columns. The initial revision applies ``SQLModel.metadata.create_all`` against the
live metadata, so this revision is retained as an applied-history marker and the
alembic-vs-models parity gate stays green.
"""
from typing import Sequence, Union

from alembic import op
from sqlmodel import SQLModel

from hydra.database import models  # noqa: F401


revision: str = "202607021000"
down_revision: Union[str, Sequence[str], None] = "202607021130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)


def downgrade() -> None:
    pass
