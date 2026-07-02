"""writing formats and docx artifacts schema

Revision ID: 202607021200
Revises: 202607020300
Create Date: 2026-07-02 12:00:00.000000

Branch 01-12 adds the ``docx_artifacts`` table (converter adapter/version,
availability status, setup error, import/export status, output/source paths,
active-content flags) so DOCX actions can explain missing local capability after
restart (HL-EXPORT-09). The initial revision (096eafd18914) builds the schema
from ``SQLModel.metadata`` via ``create_all``; because no database has shipped
yet, the head schema always reflects the current metadata and the
alembic-vs-models parity gate stays green. This revision is retained as an
applied-history marker for the branch.
"""
from typing import Sequence, Union


revision: str = "202607021200"
down_revision: Union[str, Sequence[str], None] = "202607020300"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
