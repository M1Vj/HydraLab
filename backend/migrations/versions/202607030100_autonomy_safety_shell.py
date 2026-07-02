"""autonomy safety shell

Revision ID: 202607030100
Revises: 202607021700
Create Date: 2026-07-03 01:00:00.000000

Adds Phase-3 autonomy safety metadata tables via the SQLModel create_all marker
pattern, keeping Alembic history linear with a single head.
"""
from typing import Sequence, Union

from alembic import op
from sqlmodel import SQLModel

from hydra.database import models  # noqa: F401

revision: str = "202607030100"
down_revision: Union[str, Sequence[str], None] = "202607021700"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)

def downgrade() -> None:
    pass
