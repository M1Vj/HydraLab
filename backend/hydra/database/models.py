import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow():
    return datetime.now(timezone.utc)


def uuid_text() -> str:
    return str(uuid.uuid4())


class Workspace(SQLModel, table=True):
    __tablename__ = "workspaces"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    workspace_id: Optional[str] = Field(default=None, foreign_key="workspaces.id", nullable=True)
    title: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    conversation_id: Optional[str] = Field(default=None, foreign_key="conversations.id", nullable=True)
    chat_id: Optional[str] = Field(default=None, index=True)
    role: str
    content: str
    model: Optional[str] = Field(default=None)
    provider: Optional[str] = Field(default=None)
    context_refs: str = Field(default="[]")
    trust_origin: str = Field(default="user")
    created_at: datetime = Field(default_factory=utcnow)


class Source(SQLModel, table=True):
    __tablename__ = "sources"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    workspace_id: Optional[str] = Field(default=None, foreign_key="workspaces.id", nullable=True)
    project_id: Optional[str] = Field(default=None, index=True)
    title: str
    authors: str = Field(default="")
    year: str = Field(default="")
    url: Optional[str] = None
    abstract: str = Field(default="")
    kind: str = Field(default="article")
    source_type: str = Field(default="article")
    doi: Optional[str] = Field(default=None, index=True)
    arxiv_id: Optional[str] = Field(default=None, index=True)
    metadata_json: Optional[str] = None
    metadata_sources_json: str = Field(default="[]")
    trust_origin: str = Field(default="user")
    link_state: str = Field(default="live")
    trashed: bool = Field(default=False)
    merged_into_source_id: Optional[str] = Field(default=None, nullable=True)
    added_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Note(SQLModel, table=True):
    __tablename__ = "notes"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    workspace_id: Optional[str] = Field(default=None, foreign_key="workspaces.id", nullable=True)
    project_id: Optional[str] = Field(default=None, index=True)
    relative_path: str = Field(default="")
    title: str
    body: str = Field(default="")
    source_id: Optional[str] = Field(default=None, foreign_key="sources.id", nullable=True)
    frontmatter: str = Field(default="{}")
    content_hash: str = Field(default="")
    tags: str = Field(default="[]")
    trust_origin: str = Field(default="user")
    link_state: str = Field(default="live")
    soft_deleted: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Citation(SQLModel, table=True):
    __tablename__ = "citations"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    source_id: str = Field(foreign_key="sources.id")
    project_id: Optional[str] = Field(default=None, index=True)
    text: str
    citation_key: str = Field(default="")
    csl_json: str = Field(default="{}")
    doi: Optional[str] = Field(default=None)
    link_state: str = Field(default="live")
    trust_origin: str = Field(default="user")
    created_at: datetime = Field(default_factory=utcnow)


class Claim(SQLModel, table=True):
    __tablename__ = "claims"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    workspace_id: Optional[str] = Field(default=None, foreign_key="workspaces.id", nullable=True)
    project_id: Optional[str] = Field(default=None, index=True)
    text: str
    location_type: Optional[str] = Field(default=None)
    location_id: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="needs_review")
    link_state: str = Field(default="live")
    trust_origin: str = Field(default="user")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class EvidenceLink(SQLModel, table=True):
    __tablename__ = "evidence_links"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    claim_id: str = Field(foreign_key="claims.id")
    citation_id: Optional[str] = Field(default=None, foreign_key="citations.id", nullable=True)
    source_id: str = Field(foreign_key="sources.id")
    passage: str
    support: str
    confidence: float
    review_status: str
    annotation_id: Optional[str] = Field(default=None, index=True)
    sidecar_path: Optional[str] = Field(default=None)
    sidecar_record_id: Optional[str] = Field(default=None, index=True)
    link_state: str = Field(default="live")
    trust_origin: str = Field(default="user")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Task(SQLModel, table=True):
    __tablename__ = "tasks"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    workspace_id: Optional[str] = Field(default=None, foreign_key="workspaces.id", nullable=True)
    project_id: Optional[str] = Field(default=None, index=True)
    title: str
    column_name: str
    detail: str = Field(default="")
    progress: int = Field(default=0)
    phase_indicator: str = Field(default="")
    position: int = Field(default=0)
    priority: str = Field(default="normal")
    tags: str = Field(default="[]")
    origin: str = Field(default="manual")
    assistant_created: bool = Field(default=False)
    trust_origin: str = Field(default="user")
    soft_deleted: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Setting(SQLModel, table=True):
    __tablename__ = "settings"
    key: str = Field(primary_key=True)
    workspace_id: Optional[str] = Field(default=None, foreign_key="workspaces.id", nullable=True)
    value: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ProviderSettings(SQLModel, table=True):
    __tablename__ = "provider_settings"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    provider: str = Field(index=True)
    model: str
    api_key_ref: str = Field(default="")
    auth_method: str = Field(default="api_key")
    credential_kind: str = Field(default="api_key")
    auth_status: str = Field(default="configured")
    scopes_json: str = Field(default="[]")
    secret_ref: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ActivityEvent(SQLModel, table=True):
    __tablename__ = "activity_events"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    kind: str
    message: str
    payload: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow)


class NoteLink(SQLModel, table=True):
    __tablename__ = "note_links"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    source_id: str = Field(index=True)
    source_type: str = Field(index=True)
    target_note_id: Optional[str] = Field(default=None, foreign_key="notes.id", index=True, nullable=True)
    target_source_id: Optional[str] = Field(default=None, foreign_key="sources.id", index=True, nullable=True)
    target_task_id: Optional[str] = Field(default=None, foreign_key="tasks.id", index=True, nullable=True)
    target_claim_id: Optional[str] = Field(default=None, foreign_key="claims.id", index=True, nullable=True)
    raw_target_name: str = Field(index=True)
    link_type: str = Field(default="wiki", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class SchemaVersion(SQLModel, table=True):
    __tablename__ = "schema_versions"
    component: str = Field(primary_key=True)
    version: str
    applied_at: datetime = Field(default_factory=utcnow)


class KgEdge(SQLModel, table=True):
    __tablename__ = "kg_edges"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: str = Field(index=True)
    src_id: str = Field(index=True)
    src_type: str
    dst_id_or_path: str = Field(index=True)
    dst_type: str = Field(default="unresolved")
    link_type: str = Field(default="wikilink")
    locator: str = Field(default="{}")
    resolved: bool = Field(default=False)
    dangling: bool = Field(default=False)
    link_state: str = Field(default="live")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class TaskLink(SQLModel, table=True):
    __tablename__ = "task_links"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    task_id: str = Field(index=True)
    target_type: str
    target_id_or_path: str = Field(index=True)
    link_role: str = Field(default="about")
    link_state: str = Field(default="live")
    created_at: datetime = Field(default_factory=utcnow)


class Chat(SQLModel, table=True):
    __tablename__ = "chats"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: str = Field(index=True)
    name: str
    archived: bool = Field(default=False)
    soft_deleted: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BrowserEvent(SQLModel, table=True):
    __tablename__ = "browser_events"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: str = Field(index=True)
    url: str
    title: str = Field(default="")
    captured_text_ref: Optional[str] = Field(default=None)
    selection: Optional[str] = Field(default=None)
    detected_metadata: str = Field(default="{}")
    event_type: str = Field(default="visit")
    trust_origin: str = Field(default="untrusted")
    soft_deleted: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: str = Field(index=True)
    recipe: Optional[str] = Field(default=None)
    stage: str = Field(default="")
    mode: str = Field(default="passive")
    inputs_ref: str = Field(default="[]")
    status: str = Field(default="queued")
    started_at: Optional[datetime] = Field(default=None)
    ended_at: Optional[datetime] = Field(default=None)
    artifacts: str = Field(default="[]")
    checkpoints: str = Field(default="[]")
    trust_decisions: str = Field(default="[]")
    soft_deleted: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Annotation(SQLModel, table=True):
    __tablename__ = "annotations"
    sidecar_record_id: str = Field(default_factory=uuid_text, primary_key=True)
    source_id: str = Field(index=True)
    page: int = Field(default=1)
    text: str = Field(default="")
    quad_points: str = Field(default="[]")
    bbox: str = Field(default="{}")
    type: str = Field(default="highlight")
    linked_claim_ids: str = Field(default="[]")
    linked_note_ids: str = Field(default="[]")
    color: Optional[str] = Field(default=None)
    rev: int = Field(default=1)
    content_hash: str = Field(default="")
    link_state: str = Field(default="live")
    trust_origin: str = Field(default="user")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AnnotationIndexMetadata(SQLModel, table=True):
    __tablename__ = "annotation_index_metadata"
    source_id: str = Field(primary_key=True)
    sidecar_path: str
    sidecar_content_hash: str
    indexed_at: datetime = Field(default_factory=utcnow)


class IndexQueueItem(SQLModel, table=True):
    __tablename__ = "index_queue_items"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: str = Field(index=True)
    target_type: str
    target_id_or_path: str = Field(index=True)
    status: str = Field(default="queued")
    priority: int = Field(default=0)
    retry_count: int = Field(default=0)
    paused: bool = Field(default=False)
    content_hash: str = Field(default="")
    extraction_version: int = Field(default=1)
    index_version: int = Field(default=1)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class LexicalIndexEntry(SQLModel, table=True):
    __tablename__ = "lexical_index_entries"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    source_id: str = Field(index=True)
    chunk_id: str = Field(index=True)
    locator: str = Field(default="")
    text: str = Field(default="")
    extraction_version: int = Field(default=1)
    index_version: int = Field(default=1)
    query_mode: str = Field(default="lexical")
    provider: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    semantic_ready: bool = Field(default=False)
    trust_level: str = Field(default="untrusted-external", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class DiscoveryCacheEntry(SQLModel, table=True):
    __tablename__ = "discovery_cache_entries"
    cache_key: str = Field(primary_key=True)
    provider: str = Field(index=True)
    query_hash: str = Field(index=True)
    identifier: Optional[str] = Field(default=None, index=True)
    payload_json: str
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime


class IngestionJob(SQLModel, table=True):
    __tablename__ = "ingestion_jobs"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    source_id: str = Field(foreign_key="sources.id", index=True)
    source_path: str
    status: str = Field(default="queued", index=True)
    progress: int = Field(default=0)
    priority: int = Field(default=0, index=True)
    retry_count: int = Field(default=0)
    original_content_hash: str = Field(default="")
    failure_reason: str = Field(default="")
    notes_json: str = Field(default="[]")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    started_at: Optional[datetime] = Field(default=None, nullable=True)
    completed_at: Optional[datetime] = Field(default=None, nullable=True)


class IngestionArtifact(SQLModel, table=True):
    __tablename__ = "ingestion_artifacts"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    source_id: str = Field(foreign_key="sources.id", index=True)
    job_id: Optional[str] = Field(default=None, foreign_key="ingestion_jobs.id", index=True, nullable=True)
    engine: str = Field(index=True)
    kind: str = Field(index=True)
    path: str
    content_hash: str = Field(default="")
    extraction_confidence: float = Field(default=0.0)
    trust_level: str = Field(default="untrusted-external", index=True)
    warnings_json: str = Field(default="[]")
    metadata_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow)


class ExtractedImage(SQLModel, table=True):
    __tablename__ = "extracted_images"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    source_id: str = Field(foreign_key="sources.id", index=True)
    artifact_id: Optional[str] = Field(default=None, foreign_key="ingestion_artifacts.id", nullable=True)
    path: str
    page: int = Field(default=1)
    bbox: str = Field(default="{}")
    caption: str = Field(default="")
    trust_level: str = Field(default="untrusted-external", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class ConversionWarning(SQLModel, table=True):
    __tablename__ = "conversion_warnings"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    source_id: str = Field(foreign_key="sources.id", index=True)
    job_id: Optional[str] = Field(default=None, foreign_key="ingestion_jobs.id", nullable=True)
    artifact_id: Optional[str] = Field(default=None, foreign_key="ingestion_artifacts.id", nullable=True)
    code: str = Field(index=True)
    message: str
    severity: str = Field(default="warning")
    created_at: datetime = Field(default_factory=utcnow)


class ReviewItem(SQLModel, table=True):
    __tablename__ = "review_items"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: Optional[str] = Field(default=None, index=True)
    item_type: str = Field(index=True)
    title: str
    summary: str = Field(default="")
    origin_type: Optional[str] = Field(default=None)
    origin_id: Optional[str] = Field(default=None, index=True)
    target_type: Optional[str] = Field(default=None)
    target_id: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="pending")
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SourceTombstone(SQLModel, table=True):
    __tablename__ = "source_tombstones"
    old_id: str = Field(primary_key=True)
    survivor_id: str = Field(index=True)
    object_type: str = Field(default="source")
    merged_at: datetime = Field(default_factory=utcnow)
    merge_record_id: str = Field(index=True)
    reason: str
    merge_confidence: float = Field(default=1.0)


class SourceMergeRecord(SQLModel, table=True):
    __tablename__ = "source_merge_records"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    survivor_id: str = Field(index=True)
    merged_ids_json: str
    reason: str
    reversible: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)


class MigrationIdMap(SQLModel, table=True):
    __tablename__ = "migration_id_maps"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    object_type: str = Field(index=True)
    old_id: str = Field(index=True)
    new_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow)
