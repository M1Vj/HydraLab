"""nullable ingestion job source

Revision ID: 202607030900
Revises: 202607030800
Create Date: 2026-07-03 09:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202607030900"
down_revision: Union[str, Sequence[str], None] = "202607030800"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ingestion_jobs") as batch_op:
        batch_op.alter_column(
            "source_id",
            existing_type=sa.String(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("ingestion_jobs") as batch_op:
        batch_op.alter_column(
            "source_id",
            existing_type=sa.String(),
            nullable=False,
        )
