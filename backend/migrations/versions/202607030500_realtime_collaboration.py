"""real-time collaboration

Revision ID: 202607030500
Revises: 202607030100
Create Date: 2026-07-03 05:00:00.000000

Adds Phase-3 collaboration metadata tables via the SQLModel create_all marker
pattern, keeping Alembic history linear with a single head.
"""
from typing import Sequence, Union

from alembic import op
from sqlmodel import SQLModel

from hydra.collaboration.audit import COLLABORATION_AUDIT_APPEND_ONLY_TRIGGERS
from hydra.database import models  # noqa: F401

revision: str = "202607030500"
down_revision: Union[str, Sequence[str], None] = "202607030100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)
    for statement in COLLABORATION_AUDIT_APPEND_ONLY_TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS collaborative_edit_audit_no_update")
    op.execute("DROP TRIGGER IF EXISTS collaborative_edit_audit_no_delete")
