"""tasks/git/console/exports (feature 01-11)

Revision ID: 202607021130
Revises: 202607021200
Create Date: 2026-07-02 11:30:00.000000

Note: authored on a branch off the pre-01-09 head; re-chained after 01-12
(202607021200) at merge time to keep a single linear alembic history across
the parallel Phase-1 branches (01-09, 01-11, 01-12).

Feature 01-11 adds task lifecycle/due/review columns to the ``tasks`` table (and
relies on the existing ``task_links`` / ``review_items`` tables). The initial
revision builds the current SQLModel metadata via ``create_all``, so on a fresh
Phase-1 database this revision is an applied-history marker; the alembic-head vs
SQLModel-metadata parity gate (test_database.py) proves the schemas match.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "202607021130"
down_revision: Union[str, Sequence[str], None] = "202607021200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_TASK_COLUMNS = {
    "due": sa.Column("due", sa.String(), nullable=True),
    "lifecycle_state": sa.Column("lifecycle_state", sa.String(), nullable=False, server_default="active"),
    "review_category": sa.Column("review_category", sa.String(), nullable=True),
}


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns("tasks")}
    for name, column in _NEW_TASK_COLUMNS.items():
        if name not in existing:
            op.add_column("tasks", column)


def downgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns("tasks")}
    for name in _NEW_TASK_COLUMNS:
        if name in existing:
            op.drop_column("tasks", name)
