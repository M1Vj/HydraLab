"""self-evolving skills & fixer

Revision ID: 202607030700
Revises: 202607030500
Create Date: 2026-07-03 07:00:00.000000

Adds the Phase-3 ``self_evolution_changes`` change-set table via the SQLModel
create_all marker pattern, keeping Alembic history linear with a single head. The
change row is intentionally NOT append-only — status transitions on the same row
(proposed→approved→applied|rolled_back|denied) are expected; the forensic,
append-only trail is the existing ``agent_audit_ledger`` (03-01), which already
carries its own no-update/no-delete triggers.
"""
from typing import Sequence, Union

from alembic import op
from sqlmodel import SQLModel

from hydra.database import models  # noqa: F401

revision: str = "202607030700"
down_revision: Union[str, Sequence[str], None] = "202607030500"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS self_evolution_changes")
