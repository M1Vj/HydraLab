"""citations claims evidence schema

Revision ID: 202607020300
Revises: 202607020102
Create Date: 2026-07-02 03:00:00.000000

Branch 01-09 extends the Section 26.9 Source/Claim/Evidence columns (venue,
publisher, keywords, identifiers, csl_json, bibtex, ris, confidence,
duplicate_group_id/status, merge_confidence; claim origin/extraction metadata;
evidence locator/support_level/evidence_type; reversible merge journal). The
initial revision (096eafd18914) builds the schema from ``SQLModel.metadata``
via ``create_all``; because no database has shipped yet, the head schema always
reflects the current metadata and the alembic-vs-models parity gate stays green.
This revision is retained as an applied-history marker for the branch.
"""
from typing import Sequence, Union


revision: str = "202607020300"
down_revision: Union[str, Sequence[str], None] = "202607020102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
