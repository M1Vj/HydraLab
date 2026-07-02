"""mcp tool integration (feature 02-02)

Revision ID: 202607021400
Revises: 202607021000
Create Date: 2026-07-02 14:00:00.000000

Feature 02-02 adds the MCP server/tool registry plus the per-call trace-event and
untrusted-external artifact tables. The initial revision builds the current
SQLModel metadata via ``create_all``, so on a fresh Phase-1/2 database these
tables already exist and this revision is an applied-history marker; the guards
below make it safe both on a fresh ``create_all`` database and on one migrated
incrementally. The alembic-head vs SQLModel-metadata parity gate
(test_database.py) proves the schemas match.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "202607021400"
down_revision: Union[str, Sequence[str], None] = "202607021000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "mcp_servers"):
        op.create_table(
            "mcp_servers",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("transport", sa.String(), nullable=False, server_default="stdio"),
            sa.Column("connection_json", sa.String(), nullable=False, server_default="{}"),
            sa.Column("auth_handle_ref", sa.String(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("connector", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="registered"),
            sa.Column("connection_error", sa.String(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_mcp_servers_name", "mcp_servers", ["name"])

    if not _has_table(bind, "mcp_tools"):
        op.create_table(
            "mcp_tools",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("server_id", sa.String(), sa.ForeignKey("mcp_servers.id"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=False, server_default=""),
            sa.Column("input_schema_json", sa.String(), nullable=False, server_default="{}"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("permission", sa.String(), nullable=False, server_default="deny"),
            sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_mcp_tools_server_id", "mcp_tools", ["server_id"])
        op.create_index("ix_mcp_tools_name", "mcp_tools", ["name"])

    if not _has_table(bind, "mcp_tool_call_events"):
        op.create_table(
            "mcp_tool_call_events",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("server_id", sa.String(), nullable=True),
            sa.Column("tool_id", sa.String(), nullable=True),
            sa.Column("tool_name", sa.String(), nullable=False, server_default=""),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("request_summary", sa.String(), nullable=False, server_default=""),
            sa.Column("output_summary", sa.String(), nullable=False, server_default=""),
            sa.Column("redaction", sa.String(), nullable=False, server_default="none"),
            sa.Column("content_exclusions_json", sa.String(), nullable=False, server_default="[]"),
            sa.Column("detail", sa.String(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_mcp_tool_call_events_server_id", "mcp_tool_call_events", ["server_id"])
        op.create_index("ix_mcp_tool_call_events_tool_id", "mcp_tool_call_events", ["tool_id"])
        op.create_index("ix_mcp_tool_call_events_status", "mcp_tool_call_events", ["status"])

    if not _has_table(bind, "mcp_artifacts"):
        op.create_table(
            "mcp_artifacts",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("event_id", sa.String(), sa.ForeignKey("mcp_tool_call_events.id"), nullable=False),
            sa.Column("tool_id", sa.String(), nullable=True),
            sa.Column("trust_level", sa.String(), nullable=False, server_default="untrusted-external"),
            sa.Column("content", sa.String(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_mcp_artifacts_event_id", "mcp_artifacts", ["event_id"])
        op.create_index("ix_mcp_artifacts_tool_id", "mcp_artifacts", ["tool_id"])
        op.create_index("ix_mcp_artifacts_trust_level", "mcp_artifacts", ["trust_level"])


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("mcp_artifacts", "mcp_tool_call_events", "mcp_tools", "mcp_servers"):
        if _has_table(bind, table):
            op.drop_table(table)
