"""storage settings foundation

Revision ID: 202607020102
Revises: 096eafd18914
Create Date: 2026-07-02 01:02:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "202607020102"
down_revision: Union[str, Sequence[str], None] = "096eafd18914"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column(table: str, column: sa.Column) -> None:
    with op.batch_alter_table(table) as batch_op:
        batch_op.add_column(column)


def upgrade() -> None:
    _add_column("sources", sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("sources", sa.Column("source_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="article"))
    _add_column("sources", sa.Column("doi", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("sources", sa.Column("arxiv_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("sources", sa.Column("metadata_sources_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"))
    _add_column("sources", sa.Column("trust_origin", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="user"))
    _add_column("sources", sa.Column("link_state", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="live"))
    _add_column("sources", sa.Column("trashed", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    _add_column("sources", sa.Column("merged_into_source_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("sources", sa.Column("added_at", sa.DateTime(), nullable=True))

    _add_column("notes", sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("notes", sa.Column("relative_path", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""))
    _add_column("notes", sa.Column("frontmatter", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"))
    _add_column("notes", sa.Column("content_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""))
    _add_column("notes", sa.Column("tags", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"))
    _add_column("notes", sa.Column("trust_origin", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="user"))
    _add_column("notes", sa.Column("link_state", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="live"))
    _add_column("notes", sa.Column("soft_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    _add_column("citations", sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("citations", sa.Column("citation_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""))
    _add_column("citations", sa.Column("csl_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="{}"))
    _add_column("citations", sa.Column("doi", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("citations", sa.Column("link_state", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="live"))
    _add_column("citations", sa.Column("trust_origin", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="user"))

    _add_column("claims", sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("claims", sa.Column("location_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("claims", sa.Column("location_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("claims", sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="needs_review"))
    _add_column("claims", sa.Column("link_state", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="live"))
    _add_column("claims", sa.Column("trust_origin", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="user"))

    _add_column("evidence_links", sa.Column("annotation_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("evidence_links", sa.Column("sidecar_path", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("evidence_links", sa.Column("sidecar_record_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("evidence_links", sa.Column("link_state", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="live"))
    _add_column("evidence_links", sa.Column("trust_origin", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="user"))
    _add_column("evidence_links", sa.Column("updated_at", sa.DateTime(), nullable=True))

    _add_column("tasks", sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("tasks", sa.Column("priority", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="normal"))
    _add_column("tasks", sa.Column("tags", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"))
    _add_column("tasks", sa.Column("origin", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="manual"))
    _add_column("tasks", sa.Column("assistant_created", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    _add_column("tasks", sa.Column("trust_origin", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="user"))
    _add_column("tasks", sa.Column("soft_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    _add_column("messages", sa.Column("chat_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("messages", sa.Column("model", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("messages", sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _add_column("messages", sa.Column("context_refs", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"))
    _add_column("messages", sa.Column("trust_origin", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="user"))

    _add_column("provider_settings", sa.Column("auth_method", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="api_key"))
    _add_column("provider_settings", sa.Column("credential_kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="api_key"))
    _add_column("provider_settings", sa.Column("auth_status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="configured"))
    _add_column("provider_settings", sa.Column("scopes_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"))
    _add_column("provider_settings", sa.Column("secret_ref", sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    op.create_table(
        "schema_versions",
        sa.Column("component", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("version", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("component"),
    )
    op.create_table("kg_edges", sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True), sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("src_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("src_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("dst_id_or_path", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("dst_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("link_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("locator", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("resolved", sa.Boolean(), nullable=False), sa.Column("dangling", sa.Boolean(), nullable=False), sa.Column("link_state", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("task_links", sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True), sa.Column("task_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("target_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("target_id_or_path", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("link_role", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("link_state", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("chats", sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True), sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("archived", sa.Boolean(), nullable=False), sa.Column("soft_deleted", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("browser_events", sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True), sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("url", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("captured_text_ref", sqlmodel.sql.sqltypes.AutoString(), nullable=True), sa.Column("selection", sqlmodel.sql.sqltypes.AutoString(), nullable=True), sa.Column("detected_metadata", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("event_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("trust_origin", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("soft_deleted", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("agent_runs", sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True), sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("recipe", sqlmodel.sql.sqltypes.AutoString(), nullable=True), sa.Column("stage", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("mode", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("inputs_ref", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("started_at", sa.DateTime(), nullable=True), sa.Column("ended_at", sa.DateTime(), nullable=True), sa.Column("artifacts", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("checkpoints", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("trust_decisions", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("soft_deleted", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("annotations", sa.Column("sidecar_record_id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True), sa.Column("source_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("page", sa.Integer(), nullable=False), sa.Column("text", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("quad_points", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("bbox", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("type", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("linked_claim_ids", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("linked_note_ids", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("color", sqlmodel.sql.sqltypes.AutoString(), nullable=True), sa.Column("rev", sa.Integer(), nullable=False), sa.Column("content_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("link_state", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("trust_origin", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("index_queue_items", sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True), sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("target_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("target_id_or_path", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("priority", sa.Integer(), nullable=False), sa.Column("retry_count", sa.Integer(), nullable=False), sa.Column("paused", sa.Boolean(), nullable=False), sa.Column("content_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("extraction_version", sa.Integer(), nullable=False), sa.Column("index_version", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("lexical_index_entries", sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True), sa.Column("source_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("chunk_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("locator", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("text", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("extraction_version", sa.Integer(), nullable=False), sa.Column("index_version", sa.Integer(), nullable=False), sa.Column("query_mode", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(), nullable=True), sa.Column("model", sqlmodel.sql.sqltypes.AutoString(), nullable=True), sa.Column("semantic_ready", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("review_items", sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True), sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True), sa.Column("item_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("origin_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True), sa.Column("origin_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True), sa.Column("target_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True), sa.Column("target_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True), sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("payload_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("source_tombstones", sa.Column("old_id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True), sa.Column("survivor_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("object_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("merged_at", sa.DateTime(), nullable=False), sa.Column("merge_record_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("merge_confidence", sa.Float(), nullable=False))
    op.create_table("source_merge_records", sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True), sa.Column("survivor_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("merged_ids_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("reversible", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("migration_id_maps", sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), primary_key=True), sa.Column("object_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("old_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("new_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))


def downgrade() -> None:
    for table in [
        "migration_id_maps",
        "source_merge_records",
        "source_tombstones",
        "review_items",
        "lexical_index_entries",
        "index_queue_items",
        "annotations",
        "agent_runs",
        "browser_events",
        "chats",
        "task_links",
        "kg_edges",
        "schema_versions",
    ]:
        op.drop_table(table)
