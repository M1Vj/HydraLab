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
    venue: str = Field(default="")
    publisher: str = Field(default="")
    keywords: str = Field(default="[]")
    identifiers: str = Field(default="{}")
    csl_json: str = Field(default="{}")
    bibtex: str = Field(default="")
    ris: str = Field(default="")
    confidence: float = Field(default=1.0)
    duplicate_group_id: Optional[str] = Field(default=None, index=True)
    duplicate_status: str = Field(default="none")
    merge_confidence: float = Field(default=0.0)
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
    claim_type: str = Field(default="")
    location_type: Optional[str] = Field(default=None)
    location_id: Optional[str] = Field(default=None, index=True)
    location_range: Optional[str] = Field(default=None)
    status: str = Field(default="draft")
    created_from: str = Field(default="manual")
    notes_path: Optional[str] = Field(default=None)
    origin_ref: Optional[str] = Field(default=None)
    origin_quote: str = Field(default="")
    extraction_confidence: float = Field(default=0.0)
    extraction_mode: str = Field(default="manual")
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
    asset_id: Optional[str] = Field(default=None)
    passage: str
    support: str
    support_level: str = Field(default="")
    confidence: float
    review_status: str
    evidence_type: str = Field(default="quote")
    locator: str = Field(default="{}")
    quote_text: str = Field(default="")
    summary: str = Field(default="")
    created_by: str = Field(default="user")
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
    due: Optional[str] = Field(default=None)
    priority: str = Field(default="normal")
    tags: str = Field(default="[]")
    origin: str = Field(default="manual")
    assistant_created: bool = Field(default=False)
    lifecycle_state: str = Field(default="active", index=True)
    review_category: Optional[str] = Field(default=None)
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


class BrowserHostPermission(SQLModel, table=True):
    __tablename__ = "browser_host_permissions"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: str = Field(index=True)
    host: str = Field(index=True)
    state: str = Field(default="ask")
    task_group_id: Optional[str] = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=utcnow)


class BrowserActionLog(SQLModel, table=True):
    __tablename__ = "browser_action_logs"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: str = Field(index=True)
    action: str = Field(index=True)
    host: str = Field(index=True)
    mode: str = Field(default="copilot")
    approval_result: str = Field(default="approved")
    target_url: str = Field(default="")
    task_group_id: Optional[str] = Field(default=None, index=True)
    trust_level: str = Field(default="user-curated")
    payload_json: str = Field(default="{}")
    timestamp: datetime = Field(default_factory=utcnow)


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: str = Field(index=True)
    recipe: Optional[str] = Field(default=None)
    stage: str = Field(default="")
    mode: str = Field(default="passive")
    inputs_ref: str = Field(default="[]")
    status: str = Field(default="queued")
    paused: bool = Field(default=False)
    stop_reason: str = Field(default="")
    tokens_used: int = Field(default=0)
    started_at: Optional[datetime] = Field(default=None)
    ended_at: Optional[datetime] = Field(default=None)
    artifacts: str = Field(default="[]")
    checkpoints: str = Field(default="[]")
    trust_decisions: str = Field(default="[]")
    soft_deleted: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AgentRunStep(SQLModel, table=True):
    """One incrementally-persisted step of a run trace (HL-ASSIST-04).

    Steps are flushed one row at a time so a cancelled run keeps its completed
    prefix intact; ``step_index`` preserves order independent of timestamps.
    """

    __tablename__ = "agent_run_steps"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    run_id: str = Field(foreign_key="agent_runs.id", index=True)
    step_index: int = Field(default=0)
    kind: str = Field(default="")
    status: str = Field(default="completed")
    summary: str = Field(default="")
    payload_json: str = Field(default="{}")
    tokens: int = Field(default=0)
    trust_origin: str = Field(default="user")
    skill_id: Optional[str] = Field(default=None)
    capability: Optional[str] = Field(default=None)
    denied_capability: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)


class AgentRunCandidate(SQLModel, table=True):
    """Persisted population/candidate artifact for Phase-3 Autopilot runs."""

    __tablename__ = "agent_run_candidates"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    run_id: str = Field(foreign_key="agent_runs.id", index=True)
    project_id: Optional[str] = Field(default=None, index=True)
    candidate_id: str = Field(index=True)
    candidate_artifact_json: str = Field(default="{}")
    ranking_score: float = Field(default=0.0)
    ranking_method: str = Field(default="pairwise", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class AgentApproval(SQLModel, table=True):
    """A per-item Co-pilot approval / Full-Access downgrade record (HL-MODE-02).

    Rejecting an approval mutates no workspace state; the apply callback only
    runs on an ``approved`` decision. ``target_kind``/``target_ref`` intentionally
    avoid the source-polymorphic ``*_type``/``*_id`` column-name convention.
    """

    __tablename__ = "agent_approvals"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    run_id: Optional[str] = Field(default=None, foreign_key="agent_runs.id", index=True, nullable=True)
    project_id: Optional[str] = Field(default=None, index=True)
    mode: str = Field(default="copilot")
    action_kind: str = Field(default="")
    target_kind: Optional[str] = Field(default=None)
    target_ref: Optional[str] = Field(default=None)
    summary: str = Field(default="")
    payload_json: str = Field(default="{}")
    status: str = Field(default="pending")
    decision: Optional[str] = Field(default=None)
    reason: str = Field(default="")
    trust_origin: str = Field(default="user")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AgentModePolicy(SQLModel, table=True):
    """Per-project Agent Access Mode + Full-Access opt-in (HL-MODE-01/03).

    Full Access defaults OFF and requires explicit per-project enablement.
    """

    __tablename__ = "agent_mode_policies"
    project_id: str = Field(primary_key=True)
    default_mode: str = Field(default="passive")
    full_access_enabled: bool = Field(default=False)
    autopilot_enabled: bool = Field(default=False)
    autonomy_policy_json: str = Field(default="{}")
    updated_at: datetime = Field(default_factory=utcnow)

class AgentCheckpoint(SQLModel, table=True):
    __tablename__ = "agent_checkpoints"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, foreign_key="agent_runs.id", index=True, nullable=True)
    git_ref: Optional[str] = Field(default=None)
    commit: Optional[str] = Field(default=None)
    label: str = Field(default="checkpoint")
    target: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)

class AgentAuditLedgerEntry(SQLModel, table=True):
    __tablename__ = "agent_audit_ledger"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, foreign_key="agent_runs.id", index=True, nullable=True)
    actor: str = Field(default="autopilot")
    action: str = Field(default="")
    risk_level: str = Field(default="high")
    target: str = Field(default="")
    approval_state: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


class SelfEvolutionChange(SQLModel, table=True):
    """One typed, reviewable self-evolution change (branch 03-05, HL-ASSIST-30..35).

    A change-set is a group of these rows sharing ``changeset_id``. Each row is a
    single typed diff (``category`` skill|prompt|setting|app_code) rendered as a
    human-readable ``unified_diff`` (redacted before persistence) plus the exact
    ``new_content`` payload written to ``target_path`` on apply. ``test_plan`` names
    the verification-allowlist commands that gate it; an empty plan is not
    approvable. ``risk_class`` (auto_eligible|review_required) and ``trust_level``
    (user|untrusted-external) force protected-field and untrusted-traced proposals
    to the Review Inbox and bar them from the apply path. Status transitions on the
    same row are expected (proposed→approved→applied|rolled_back|denied); the
    forensic trail is the append-only ``agent_audit_ledger``.
    """

    __tablename__ = "self_evolution_changes"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    changeset_id: str = Field(default="", index=True)
    change_id: str = Field(default_factory=uuid_text, index=True)
    category: str = Field(default="prompt")  # skill | prompt | setting | app_code
    target_path: str = Field(default="")
    unified_diff: str = Field(default="")  # redacted, human-readable
    new_content: str = Field(default="")  # payload written to target_path on apply
    test_plan: str = Field(default="[]")  # json list[str] of allowlisted commands
    risk_class: str = Field(default="auto_eligible")  # auto_eligible | review_required
    risk_reason: str = Field(default="")
    trust_level: str = Field(default="user")  # user | untrusted-external
    origin: str = Field(default="user")
    status: str = Field(default="proposed")  # proposed|approved|applied|rolled_back|denied
    checkpoint_ref: Optional[str] = Field(default=None)
    verification_result: str = Field(default="")  # pass | fail | ""
    review_inbox: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ProjectCollaborationSettings(SQLModel, table=True):
    __tablename__ = "project_collaboration_settings"
    project_id: str = Field(primary_key=True)
    enabled: bool = Field(default=False)
    sync_server_url: str = Field(default="")
    sync_server_kind: str = Field(default="self-hosted")
    updated_at: datetime = Field(default_factory=utcnow)


class CollaboratorIdentity(SQLModel, table=True):
    __tablename__ = "collaborator_identities"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    display_name: str = Field(index=True)
    auth_token_hash: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    revoked_at: Optional[datetime] = Field(default=None, nullable=True)


class ProjectCollaborationPermission(SQLModel, table=True):
    __tablename__ = "project_collaboration_permissions"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: str = Field(index=True)
    collaborator_id: str = Field(foreign_key="collaborator_identities.id", index=True)
    permission: str = Field(index=True)
    invite_token_hash: str = Field(default="", index=True)
    invited_at: datetime = Field(default_factory=utcnow)
    authenticated_at: Optional[datetime] = Field(default=None, nullable=True)
    revoked_at: Optional[datetime] = Field(default=None, nullable=True)


class CollaborativeEditAuditEntry(SQLModel, table=True):
    __tablename__ = "collaborative_edit_audit"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: str = Field(index=True)
    collaborator_id: str = Field(index=True)
    document_id: str = Field(index=True)
    change_summary: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


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
    reversed: bool = Field(default=False)
    repoint_log_json: str = Field(default="[]")
    created_at: datetime = Field(default_factory=utcnow)


class DocxArtifact(SQLModel, table=True):
    __tablename__ = "docx_artifacts"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: Optional[str] = Field(default=None, index=True)
    manuscript: str = Field(default="", index=True)
    kind: str = Field(default="export")  # import | export | availability
    converter_adapter: str = Field(default="")
    converter_version: str = Field(default="")
    availability_status: str = Field(default="unavailable")  # available | unavailable
    setup_error: str = Field(default="")
    status: str = Field(default="")  # success | failed | rejected | unavailable
    source_path: Optional[str] = Field(default=None)
    output_path: Optional[str] = Field(default=None)
    error_detail: str = Field(default="")
    flags_json: str = Field(default="[]")
    metadata_json: str = Field(default="{}")
    trust_origin: str = Field(default="user")
    created_at: datetime = Field(default_factory=utcnow)


class DocxEditPlan(SQLModel, table=True):
    """A reviewable set of typed OpenXML structural edits for one working DOCX.

    The plan owns the target working DOCX (under ``writing/manuscripts/``), the
    pre-apply checkpoint reference and the plan-level lifecycle status so apply
    and rollback are auditable (HL-WRITE-33/36). Operations reference it by
    ``plan_id``. Rows are SQLite-canonical and survive force-quit (HL-WRITE-32).
    """

    __tablename__ = "docx_edit_plans"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: Optional[str] = Field(default=None, index=True)
    manuscript: str = Field(default="", index=True)
    target_relpath: str = Field(default="")
    status: str = Field(default="draft")  # draft | applied | rolled_back | failed
    mode: str = Field(default="passive")  # passive | copilot | full_access
    checkpoint_ref: Optional[str] = Field(default=None)
    trust_level: str = Field(default="trusted")  # trusted | untrusted-external
    summary: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class DocxEditOperation(SQLModel, table=True):
    """One typed, inspectable OpenXML structural edit (HL-WRITE-31/32).

    Never an opaque whole-file rewrite: each row is a single structural op with a
    stable ``target_locator``, human before/after summaries, a JSON payload, and
    the review/validation/trust state that gates whether it may ever be applied.
    """

    __tablename__ = "docx_edit_operations"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    plan_id: str = Field(foreign_key="docx_edit_plans.id", index=True)
    op_type: str = Field(default="other")  # replace_text|insert_paragraph|apply_style|update_table|update_citation|comment|delete|other
    target_locator: str = Field(default="")
    location_label: str = Field(default="")
    before_summary: str = Field(default="")
    after_summary: str = Field(default="")
    payload: str = Field(default="{}")  # json
    risk_label: str = Field(default="low")  # low | medium | high
    review_status: str = Field(default="pending")  # pending | approved | rejected
    validation_status: str = Field(default="unvalidated")  # unvalidated | valid | invalid
    applied: bool = Field(default=False)
    rollback_ref: Optional[str] = Field(default=None)
    trust_level: str = Field(default="trusted", index=True)  # trusted | untrusted-external
    justification: str = Field(default="")
    motivating_excerpt: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class MigrationIdMap(SQLModel, table=True):
    __tablename__ = "migration_id_maps"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    object_type: str = Field(index=True)
    old_id: str = Field(index=True)
    new_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow)


class McpServer(SQLModel, table=True):
    """MCP server registry (HL-ASSIST-01, Section 25.7).

    Stores transport/connection config and a keychain *reference* to the auth
    handle (never a raw secret). ``enabled`` defaults to ``False``; a server is
    inert until the researcher turns it on.
    """

    __tablename__ = "mcp_servers"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    name: str = Field(index=True)
    transport: str = Field(default="stdio")  # stdio | http | inproc
    connection_json: str = Field(default="{}")  # transport/connection config
    auth_handle_ref: Optional[str] = Field(default=None)  # keychain:* reference only
    enabled: bool = Field(default=False)
    connector: Optional[str] = Field(default=None)  # e.g. "zotero-local" for connector contracts
    status: str = Field(default="registered")  # registered | connected | failed
    connection_error: str = Field(default="")  # populated on failure state
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class McpTool(SQLModel, table=True):
    """Discovered MCP tool as a managed capability (HL-ASSIST-02/03).

    Every discovered tool persists ``enabled=False`` and ``permission='deny'``;
    it is not callable until explicitly enabled/allowed.
    """

    __tablename__ = "mcp_tools"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    server_id: str = Field(foreign_key="mcp_servers.id", index=True)
    name: str = Field(index=True)
    description: str = Field(default="")
    input_schema_json: str = Field(default="{}")
    enabled: bool = Field(default=False)
    permission: str = Field(default="deny")  # allow | deny (resolved before invocation)
    read_only: bool = Field(default=False)  # connector contract advertises read-only
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class McpToolCallEvent(SQLModel, table=True):
    """Exactly one trace event per attempted MCP tool call (HL-ASSIST-04).

    Records tool id, status, request/output summaries, redaction applied and any
    content-type exclusions enforced by the consent gate.
    """

    __tablename__ = "mcp_tool_call_events"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    server_id: Optional[str] = Field(default=None, index=True)
    tool_id: Optional[str] = Field(default=None, index=True)
    tool_name: str = Field(default="")
    status: str = Field(index=True)  # allowed-completed | denied | error
    request_summary: str = Field(default="")
    output_summary: str = Field(default="")
    redaction: str = Field(default="none")
    content_exclusions_json: str = Field(default="[]")
    detail: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


class McpArtifact(SQLModel, table=True):
    """Retained result of a completed MCP tool call, tagged untrusted-external.

    Linked to its trace event (HL-ASSIST-05, Section 34.1). Tool output re-enters
    the model only through the delimited untrusted region (HL-TRUST-01).
    """

    __tablename__ = "mcp_artifacts"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    event_id: str = Field(foreign_key="mcp_tool_call_events.id", index=True)
    tool_id: Optional[str] = Field(default=None, index=True)
    trust_level: str = Field(default="untrusted-external", index=True)
    content: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


class ContextFileChange(SQLModel, table=True):
    """Append-only log of automated/manual edits to the four context files.

    Global files (SOUL/USER/MEMORY) are logs-only; HYDRA.md is Git/checkpoint-backed.
    """

    __tablename__ = "context_file_changes"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    project_id: Optional[str] = Field(default=None, index=True)
    profile_id: str = Field(default="default", index=True)
    file: str = Field(index=True)  # SOUL.md / USER.md / MEMORY.md / HYDRA.md
    change_type: str = Field(default="update")  # update / condense / manual_edit
    timing: str = Field(default="immediate")  # immediate / batched
    criticality: str = Field(default="normal")  # critical / normal
    trust_level: str = Field(default="trusted")  # trusted / untrusted-external
    provenance: str = Field(default="assistant")  # user / assistant / untrusted-external
    summary: str = Field(default="")
    checkpoint_ref: Optional[str] = Field(default=None)  # Git/checkpoint id for HYDRA.md
    logs_only: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)


class IdeaCandidate(SQLModel, table=True):
    """A saved idea-generation candidate artifact (branch 02-06, HL-ASSIST-04).

    Every field of the canonical candidate schema is persisted so a candidate
    round-trips. ``evidence_links``/``required_sources`` hold resolvable refs to
    existing source/evidence ids as JSON (never fabricated free text, DEC-11);
    they are intentionally NOT source-FK columns, so no entry is added to the
    Repository source FK-repoint registry. ``parent_candidate_id`` records single
    Evolve-pass lineage (HL-ASSIST-09). ``rubric_results`` carries the normalized
    Compare output (per-criterion value/rationale/stage_run_id/source_refs,
    HL-ASSIST-06/07); it stays empty when Compare is disabled (HL-ASSIST-08).
    """

    __tablename__ = "idea_candidates"
    id: str = Field(default_factory=uuid_text, primary_key=True)
    run_id: str = Field(foreign_key="agent_runs.id", index=True)
    project_id: Optional[str] = Field(default=None, index=True)
    title: str = Field(default="")
    short_hypothesis: str = Field(default="")
    research_question: str = Field(default="")
    motivation: str = Field(default="")
    method_sketch: str = Field(default="")
    expected_contribution: str = Field(default="")
    required_sources: str = Field(default="[]")  # json list of source ids
    evidence_links: str = Field(default="[]")  # json list of {source_id, evidence_id?}
    novelty_claim: str = Field(default="")
    feasibility_notes: str = Field(default="")
    risks: str = Field(default="")
    estimated_effort: str = Field(default="")
    generated_by_stage: str = Field(default="generate")  # generate | evolve
    parent_candidate_id: Optional[str] = Field(
        default=None, foreign_key="idea_candidates.id", index=True, nullable=True
    )
    status: str = Field(default="draft", index=True)  # draft|reviewed|ranked|promoted|rejected
    critique: str = Field(default="{}")  # json {weaknesses, risks, missing_evidence}
    rubric_results: str = Field(default="[]")  # json RubricResult list (empty when Compare off)
    rank: Optional[int] = Field(default=None)
    trust_origin: str = Field(default="user")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
