"""reproducibility evaluation ledger

Revision ID: 202607030800
Revises: 202607030700
Create Date: 2026-07-03 08:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
from sqlmodel import SQLModel

from hydra.database import models  # noqa: F401

revision: str = "202607030800"
down_revision: Union[str, Sequence[str], None] = "202607030700"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS evaluation_results")
    op.execute("DROP TABLE IF EXISTS reproducibility_manifests")
