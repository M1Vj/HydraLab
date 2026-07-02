from typing import Literal

from pydantic import BaseModel, Field, field_validator

from hydra.browser_bridge import SOURCE_POLICIES, TRUST_LEVEL_UNTRUSTED


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=800)


class SourceSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)


class SourceDiscoveryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    project_id: str | None = Field(default=None, max_length=200)
    offline_only: bool = False
    scholarly_apis_enabled: bool = True
    contact_email: str = Field(default="research@hydralab.local", max_length=320)


class SourceSaveRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    query: str = Field(default="", max_length=400)
    result: dict[str, object]
    user_initiated: bool = False
    source_origin: Literal["discovery", "browser"] = "discovery"
    browser_context_event_id: str | None = Field(default=None, max_length=200)
    save_pdf: bool = False
    automatic_pdf_download: bool = False
    allowed_pdf_domains: list[str] = Field(default_factory=list)


class WritingReviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class NoteCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    source_id: str | None = None


class NoteUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    source_id: str | None = None


class NoteFileSaveRequest(BaseModel):
    content: str = Field(max_length=2_000_000)


class NoteSuggestionRequest(BaseModel):
    suggestion_id: str = Field(min_length=1, max_length=200)
    replacement: str = Field(max_length=20000)
    auto_apply: bool = False
    origin_excerpt: str = Field(default="", max_length=12000)



TASK_TARGET_TYPES = (
    "source",
    "paper",
    "note",
    "claim",
    "citation",
    "chat",
    "browser_event",
    "annotation",
    "draft",
    "manuscript",
)
TASK_LINK_ROLES = ("about", "blocks", "derived_from", "follow_up", "evidence_for", "reviews")


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    column: str = "to_do"
    detail: str = ""
    progress: int = Field(default=0, ge=0, le=100)
    phase_indicator: str = ""
    position: int = 0
    due: str | None = Field(default=None, max_length=40)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    tags: list[str] = Field(default_factory=list)
    project_id: str | None = Field(default=None, max_length=200)


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    column: str | None = None
    detail: str | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    phase_indicator: str | None = None
    position: int | None = None
    due: str | None = Field(default=None, max_length=40)
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    tags: list[str] | None = None


class TaskLinkCreateRequest(BaseModel):
    target_type: str = "source"
    target_id_or_path: str = Field(min_length=1, max_length=1000)
    link_role: str = "about"

    @field_validator("target_type")
    @classmethod
    def _valid_target(cls, value: str) -> str:
        if value not in TASK_TARGET_TYPES:
            raise ValueError("unsupported task_link target_type")
        return value

    @field_validator("link_role")
    @classmethod
    def _valid_role(cls, value: str) -> str:
        if value not in TASK_LINK_ROLES:
            raise ValueError("unsupported task_link role")
        return value


class TaskSuggestRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    project_id: str | None = Field(default=None, max_length=200)
    origin: Literal["assistant", "auto"] = "assistant"
    category: str | None = Field(default=None, max_length=80)
    trust_origin: Literal["user", "untrusted"] = "user"
    summary: str = Field(default="", max_length=2000)
    detail: str = Field(default="", max_length=4000)
    origin_type: str | None = Field(default=None, max_length=80)
    origin_id: str | None = Field(default=None, max_length=1000)
    link: dict[str, str] | None = None
    tags: list[str] = Field(default_factory=list)


class GitInitRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    confirm: bool = False


class GitCommitRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    message: str = Field(min_length=1, max_length=1000)
    paths: list[str] | None = None


class GitRestoreRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    path: str = Field(min_length=1, max_length=1000)
    ref: str = Field(default="HEAD", max_length=200)


class GitDestructiveRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    subcommand: Literal["reset", "checkout", "clean", "rebase", "merge", "push"]
    args: list[str] = Field(default_factory=list)
    approved: bool = False


class ConsoleRunRequest(BaseModel):
    command: str = Field(min_length=1, max_length=400)
    project_id: str = Field(default="default", max_length=200)
    trigger: Literal["user", "assistant", "untrusted"] = "user"
    approve: bool = False


class CitationExportRequest(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    format: Literal["bibtex", "csl", "ris"] = "bibtex"


class ProjectZipRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    selected_files: list[str] | None = None
    include_chats: bool = False
    include_agent_logs: bool = False
    include_browser_snapshots: bool = False
    include_annotations: bool = False


class BackupRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)


class RestoreRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    reindex: bool = True


class CitationCreateRequest(BaseModel):
    source_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)

class ClaimCreateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1200)

class ClaimDetectRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)

class EvidenceCreateRequest(BaseModel):
    claim_id: str = Field(min_length=1, max_length=200)
    citation_id: str | None = None
    source_id: str = Field(min_length=1, max_length=200)
    passage: str = Field(min_length=1, max_length=4000)
    support: str = Field(pattern="^(supported|weak|unsupported)$")
    confidence: float = Field(ge=0, le=1)
    review_status: str = Field(default="needs_review", pattern="^(needs_review|accepted|rejected)$")


class AnnotationCreateRequest(BaseModel):
    page: int = Field(ge=1)
    text: str = Field(default="", max_length=12000)
    quad_points: list[float] = Field(min_length=8, max_length=8)
    type: Literal["highlight", "underline", "note"] = "highlight"
    color: str = Field(default="yellow", max_length=40)
    linked_claim_ids: list[str] = Field(default_factory=list)
    linked_note_ids: list[str] = Field(default_factory=list)


class AnnotationClaimRequest(BaseModel):
    auto_create: bool = False


class ProviderSettingsRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    api_key_ref: str = Field(default="", max_length=300)


class ProviderSecretRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    secret: str = Field(min_length=1, max_length=4000)

class SettingsUpdateRequest(BaseModel):
    provider_settings: list[ProviderSettingsRequest] | None = None
    workspace_preferences: dict[str, str] | None = None


class BrowserHandshakeRequest(BaseModel):
    handshake_nonce: str = Field(min_length=8, max_length=200)


class BrowserCaptureRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="", max_length=500)
    page_text: str = Field(default="", max_length=64000)
    selection: str = Field(default="", max_length=12000)
    event_type: str = Field(default="capture", pattern="^(capture|selection|navigation|snapshot|save)$")
    source_policy: Literal["auto-source", "context-only", "always-ask", "blocked"] = "always-ask"
    browser_integration_enabled: bool = False
    g2_local_capture: bool = False
    browser_page_text_to_provider: bool = False
    host_permission: Literal["allow-for-project", "always-allow-host", "blocked", "unknown"] = "unknown"
    incognito: bool = False
    has_credential_fields: bool = False
    has_payment_fields: bool = False
    is_project_relevant: bool = True
    metadata: dict[str, object] = Field(default_factory=dict)
    trust_level: Literal["untrusted-external"] = TRUST_LEVEL_UNTRUSTED

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if "://" not in value:
            raise ValueError("url must include a scheme")
        return value

    @field_validator("source_policy")
    @classmethod
    def validate_source_policy(cls, value: str) -> str:
        if value not in SOURCE_POLICIES:
            raise ValueError("unsupported source policy")
        return value


class BrowserHistoryRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)
class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str = Field(min_length=1)

class ChatCompletionRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1)

class ChatMessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: float

class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: float

class SourceIngestRequest(BaseModel):
    url: str | None = None
    title: str | None = None
    doi: str | None = None

class SourceRetrieveResponse(BaseModel):
    id: str
    title: str
    url: str | None
    metadata_json: str | None
    summary: str | None

class RAGRetrieveRequest(BaseModel):
    query: str
    source_id: str | None = None
