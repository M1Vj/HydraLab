"""browser co-pilot host permissions and action log

Revision ID: 202607021600
Revises: 202607021500
Create Date: 2026-07-02 16:00:00.000000

Adds BrowserHostPermission and BrowserActionLog via the same idempotent
SQLModel.metadata.create_all history-marker pattern used by the current head.
"""
from typing import Sequence, Union

from alembic import op
from sqlmodel import SQLModel

from hydra.database import models  # noqa: F401


revision: str = "202607021600"
down_revision: Union[str, Sequence[str], None] = "202607021500"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)


def downgrade() -> None:
    pass
