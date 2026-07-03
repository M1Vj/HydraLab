"""idea generation & ranking candidate artifacts

Revision ID: 202607021700
Revises: 202607021600
Create Date: 2026-07-02 17:00:00.000000

Adds the ``idea_candidates`` table for the Phase-2 idea-generation/ranking recipe
(branch 02-06) via the same idempotent ``SQLModel.metadata.create_all``
history-marker pattern used by the current head, keeping history linear (single
head) and the alembic-head vs SQLModel-metadata parity gate green.
"""
from typing import Sequence, Union

from alembic import op
from sqlmodel import SQLModel

from hydra.database import models  # noqa: F401


revision: str = "202607021700"
down_revision: Union[str, Sequence[str], None] = "202607021600"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)


def downgrade() -> None:
    pass
