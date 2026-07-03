"""collaboration document update log

Revision ID: 202607031000
Revises: 202607030900
Create Date: 2026-07-03 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
from sqlmodel import SQLModel

from hydra.database import models  # noqa: F401

revision: str = "202607031000"
down_revision: Union[str, Sequence[str], None] = "202607030900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS collaboration_updates")
