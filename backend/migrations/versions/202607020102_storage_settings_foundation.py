"""storage settings foundation

Revision ID: 202607020102
Revises: 096eafd18914
Create Date: 2026-07-02 01:02:00.000000

This revision is retained as an applied-history marker. The preceding initial
revision creates the current Phase-1 metadata exactly because no database has
shipped yet.
"""
from typing import Sequence, Union


revision: str = "202607020102"
down_revision: Union[str, Sequence[str], None] = "096eafd18914"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
