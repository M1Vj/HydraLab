import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlmodel import Field, SQLModel, Relationship


def utcnow():
    return datetime.now(timezone.utc)


class Workspace(SQLModel, table=True):
    __tablename__ = "workspaces"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    workspace_id: Optional[str] = Field(default=None, foreign_key="workspaces.id", nullable=True)
    title: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id")
    role: str # user, assistant, system, status
    content: str
    created_at: datetime = Field(default_factory=utcnow)


class Source(SQLModel, table=True):
    __tablename__ = "sources"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    workspace_id: Optional[str] = Field(default=None, foreign_key="workspaces.id", nullable=True)
    title: str
    authors: str = Field(default="")
    year: str = Field(default="")
    url: Optional[str] = None
    abstract: str = Field(default="")
    kind: str = Field(default="article")
    metadata_json: Optional[str] = None # JSON string for extra data
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Note(SQLModel, table=True):
    __tablename__ = "notes"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    workspace_id: Optional[str] = Field(default=None, foreign_key="workspaces.id", nullable=True)
    title: str
    body: str
    source_id: Optional[str] = Field(default=None, foreign_key="sources.id", nullable=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Citation(SQLModel, table=True):
    __tablename__ = "citations"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    source_id: str = Field(foreign_key="sources.id")
    text: str
    created_at: datetime = Field(default_factory=utcnow)


class Claim(SQLModel, table=True):
    __tablename__ = "claims"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    workspace_id: Optional[str] = Field(default=None, foreign_key="workspaces.id", nullable=True)
    text: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class EvidenceLink(SQLModel, table=True):
    __tablename__ = "evidence_links"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    claim_id: str = Field(foreign_key="claims.id")
    citation_id: Optional[str] = Field(default=None, foreign_key="citations.id", nullable=True)
    source_id: str = Field(foreign_key="sources.id")
    passage: str
    support: str # supported, weak, unsupported
    confidence: float
    review_status: str # needs_review, accepted, rejected
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Task(SQLModel, table=True):
    __tablename__ = "tasks"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    workspace_id: Optional[str] = Field(default=None, foreign_key="workspaces.id", nullable=True)
    title: str
    column_name: str # e.g. to_do, in_progress, review, done
    detail: str = Field(default="")
    progress: int = Field(default=0)
    phase_indicator: str = Field(default="")
    position: int = Field(default=0)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Setting(SQLModel, table=True):
    __tablename__ = "settings"
    key: str = Field(primary_key=True)
    workspace_id: Optional[str] = Field(default=None, foreign_key="workspaces.id", nullable=True)
    value: str # JSON or plain text
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ProviderSettings(SQLModel, table=True):
    __tablename__ = "provider_settings"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    provider: str = Field(index=True)
    model: str
    api_key_ref: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ActivityEvent(SQLModel, table=True):
    __tablename__ = "activity_events"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    kind: str
    message: str
    payload: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow)


class NoteLink(SQLModel, table=True):
    __tablename__ = "note_links"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    source_id: str = Field(index=True) # ID of note/task containing link
    source_type: str = Field(index=True) # "note", "task"
    target_note_id: Optional[str] = Field(default=None, foreign_key="notes.id", index=True, nullable=True)
    target_source_id: Optional[str] = Field(default=None, foreign_key="sources.id", index=True, nullable=True)
    target_task_id: Optional[str] = Field(default=None, foreign_key="tasks.id", index=True, nullable=True)
    target_claim_id: Optional[str] = Field(default=None, foreign_key="claims.id", index=True, nullable=True)
    raw_target_name: str = Field(index=True)
    link_type: str = Field(default="wiki", index=True)
    created_at: datetime = Field(default_factory=utcnow)
