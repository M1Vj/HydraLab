"""docx edit plans and operations schema (branch 02-08)

Revision ID: 202607021300
Revises: 202607021000
Create Date: 2026-07-02 13:00:00.000000

Branch 02-08 adds the ``docx_edit_plans`` and ``docx_edit_operations`` tables so
AI-assisted DOCX edits are persisted as typed, inspectable OpenXML structural
operations with review/validation/trust state and a rollback checkpoint
(HL-WRITE-31/32/33/36). As with the other Phase-1/2 markers, the initial
revision (096eafd18914) builds the schema from ``SQLModel.metadata`` via
``create_all``; because no database has shipped yet, the head schema always
reflects the current metadata and the alembic-vs-models parity gate stays green.
This revision is retained as an applied-history marker for the branch.
"""
from typing import Sequence, Union


revision: str = "202607021300"
down_revision: Union[str, Sequence[str], None] = "202607021000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
