from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from hydra.browser_bridge import SOURCE_POLICIES, TRUST_LEVEL_UNTRUSTED


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=800)


class SourceSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)


class BrowserHostPermissionUpdateRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    host: str = Field(min_length=1, max_length=255)
    state: Literal["ask", "allow_for_task", "always_allow_host", "blocked"]
    task_group_id: str | None = Field(default=None, max_length=200)


class BrowserCopilotActionRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    action: Literal["search", "save-source", "save-snapshot", "extract-metadata", "create-note"]
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="", max_length=400)
    page_text: str = Field(default="", max_length=200000)
    host: str = Field(default="", max_length=255)
    mode: Literal["copilot"] = "copilot"
    task_group_id: str | None = Field(default=None, max_length=200)
    task_group_label: str = Field(default="", max_length=200)
    user_triggered: bool = False


class AutonomousBrowserRunStartRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    task_id: str = Field(min_length=1, max_length=200)
    task_label: str = Field(min_length=1, max_length=200)
    start_urls: list[str] = Field(min_length=1, max_length=20)

    @field_validator("start_urls")
    @classmethod
    def validate_start_urls(cls, value: list[str]) -> list[str]:
        for url in value:
            if "://" not in url:
                raise ValueError("url must include a scheme")
        return value


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


class ManuscriptExportRequest(BaseModel):
    source_file: str = Field(min_length=1, max_length=400)
    output_name: str | None = Field(default=None, max_length=400)
    include_bibliography: bool = False
    project_id: str | None = Field(default=None, max_length=200)

    @field_validator("source_file", "output_name")
    @classmethod
    def reject_traversal(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if ".." in value or value.startswith("/") or "\\" in value or "\x00" in value:
            raise ValueError("path traversal is not allowed")
        return value

class ManuscriptPackageRequest(BaseModel):
    approval_id: str | None = Field(default=None, max_length=200)
    targets: list[Literal["docx", "latex", "html", "pdf"]] = Field(default_factory=lambda: ["docx", "latex", "html", "pdf"])
    acknowledge_citation_issues: bool = False
    acknowledged_redaction_item_ids: list[str] = Field(default_factory=list)
    project_id: str = Field(default="default", max_length=200)

class ManuscriptSubmissionRequest(BaseModel):
    venue: str = Field(min_length=1, max_length=200)
    approval_id: str | None = Field(default=None, max_length=200)
    project_id: str = Field(default="default", max_length=200)


class DocxEditProposalIn(BaseModel):
    op_type: str = Field(min_length=1, max_length=40)
    target_locator: str = Field(default="", max_length=400)
    payload: dict[str, object] = Field(default_factory=dict)
    justification: str = Field(default="", max_length=4000)
    justification_source: Literal["assistant", "document"] = "assistant"
    motivating_excerpt: str = Field(default="", max_length=4000)


class DocxEditPlanRequest(BaseModel):
    manuscript: str = Field(min_length=1, max_length=200)
    source_file: str = Field(min_length=1, max_length=400)
    mode: Literal["passive", "copilot", "full_access"] = "passive"
    project_id: str | None = Field(default=None, max_length=200)
    proposals: list[DocxEditProposalIn] = Field(default_factory=list)

    @field_validator("manuscript", "source_file")
    @classmethod
    def reject_docx_traversal(cls, value: str) -> str:
        if ".." in value or value.startswith("/") or "\\" in value or "\x00" in value:
            raise ValueError("path traversal is not allowed")
        return value


class DocxOperationReviewRequest(BaseModel):
    decision: Literal["approved", "rejected", "pending"]


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


class CitationRenderRequest(BaseModel):
    source_ids: list[str] = Field(default_factory=list, max_length=5000)
    style: str | None = Field(default=None, max_length=80)
    manuscript: str | None = Field(default=None, max_length=200)
    html: bool = False


class SourceImportRequest(BaseModel):
    format: Literal["bibtex", "ris", "csl-json", "csl_json", "json"] = "bibtex"
    content: str = Field(min_length=1, max_length=8_000_000)
    project_id: str | None = Field(default=None, max_length=200)


class SourceMergeRequest(BaseModel):
    source_ids: list[str] = Field(min_length=2, max_length=50)
    reason: Literal["exact_identifier", "exact_hash", "user_confirmed_fuzzy"] = "user_confirmed_fuzzy"
    merge_confidence: float = Field(default=1.0, ge=0, le=1)


class SourceUnmergeRequest(BaseModel):
    merge_record_id: str = Field(min_length=1, max_length=200)


class SourceTrashRequest(BaseModel):
    confirmed: bool = False


class ClaimCreateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    project_id: str | None = Field(default=None, max_length=200)
    claim_type: str = Field(default="", max_length=80)
    location_type: Literal["note", "draft", "chat", "source", "manuscript"] | None = None
    location_id: str | None = Field(default=None, max_length=400)
    status: Literal["draft", "needs_review", "rejected"] = "draft"
    extraction_mode: Literal["manual", "suggested", "auto_draft"] = "manual"
    origin_ref: str | None = Field(default=None, max_length=400)
    origin_quote: str = Field(default="", max_length=12000)
    extraction_confidence: float = Field(default=0.0, ge=0, le=1)


class ClaimPromoteRequest(BaseModel):
    status: Literal["draft", "supported", "weak", "contradicted", "needs_review", "rejected"]
    reviewed: bool = False


class ClaimDetectRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    location_type: Literal["note", "draft", "chat", "source", "manuscript"] | None = None
    location_id: str | None = Field(default=None, max_length=400)
    origin_ref: str | None = Field(default=None, max_length=400)
    auto_create: bool = False

class EvidenceCreateRequest(BaseModel):
    claim_id: str = Field(min_length=1, max_length=200)
    citation_id: str | None = None
    source_id: str = Field(min_length=1, max_length=200)
    passage: str = Field(min_length=1, max_length=4000)
    support: str = Field(pattern="^(supported|weak|unsupported)$")
    confidence: float = Field(ge=0, le=1)
    review_status: str = Field(default="needs_review", pattern="^(needs_review|accepted|rejected)$")
    evidence_type: Literal["quote", "summary", "figure", "table", "method", "result", "contradiction"] = "quote"
    support_level: str = Field(default="", max_length=40)
    locator: dict[str, object] = Field(default_factory=dict)
    quote_text: str = Field(default="", max_length=8000)
    summary: str = Field(default="", max_length=8000)
    annotation_id: str | None = None
    sidecar_record_id: str | None = None
    sidecar_path: str | None = None
    asset_id: str | None = None
    created_by: str = Field(default="user", max_length=40)


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


class CollaborationSettingsRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    enabled: bool = False
    sync_server_url: str = Field(default="", max_length=500)


class CollaborationInviteRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    permission: Literal["read", "comment", "edit"]


class CollaborationAuthenticateRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    invite_token: str = Field(min_length=8, max_length=200)


class CollaborationRevokeRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)


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

class ContextRef(BaseModel):
    type: str = Field(min_length=1, max_length=40)
    id_or_path: str = Field(default="", max_length=2000)
    locator: dict[str, object] = Field(default_factory=dict)
    label: str = Field(default="", max_length=400)
    text: str = Field(default="", max_length=200000)


class ChatCompletionRequest(BaseModel):
    conversation_id: str | None = None
    chat_id: str | None = None
    project_id: str = Field(default="default", max_length=200)
    message: str = Field(min_length=1)
    context_refs: list[ContextRef] = Field(default_factory=list)


class ChatCreateRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    name: str = Field(min_length=1, max_length=200)


class ChatUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    archived: bool | None = None


class ChatExportRequest(BaseModel):
    message_ids: list[str] = Field(default_factory=list)


class SendScopeRequest(BaseModel):
    context_refs: list[ContextRef] = Field(default_factory=list)


class ContextFileSaveRequest(BaseModel):
    content: str = Field(max_length=2_000_000)


class MemoryCandidateRequest(BaseModel):
    fact: str = Field(min_length=1, max_length=4000)
    destination: str = Field(default="MEMORY.md", max_length=80)
    category: str = Field(default="organization_update", max_length=80)
    confidence: float = Field(default=0.5, ge=0, le=1)
    source_ref: str = Field(default="", max_length=2000)
    trust_origin: str = Field(default="trusted", max_length=40)

class AgentModeUpdateRequest(BaseModel):
    mode: str = Field(max_length=40)
    project_id: str = Field(default="default", max_length=200)


class FullAccessUpdateRequest(BaseModel):
    enabled: bool = False
    project_id: str = Field(default="default", max_length=200)


class SkillEnabledRequest(BaseModel):
    enabled: bool = False


class SkillEditRequest(BaseModel):
    text: str = Field(max_length=200_000)


class ApprovalResolveRequest(BaseModel):
    decision: str = Field(max_length=40)


class OrchestratorRunStartRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    enabled_stages: dict[str, bool] = Field(default_factory=dict)
    scoring_method: Literal["pairwise", "tournament", "elo", "rubric"] = "pairwise"
    recipe_id: str | None = Field(default=None, max_length=120)
    recipe_inputs: dict[str, Any] = Field(default_factory=dict)


class AutonomyPolicyRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    autopilot_enabled: bool = False
    mode: Literal["passive", "copilot", "full_access"] = "passive"
    allowed_action_types: list[str] = Field(default_factory=list)
    blocked_action_types: list[str] = Field(default_factory=list)
    budget_limits: dict[str, int] = Field(default_factory=lambda: {"tokens": 60000, "wall_clock_seconds": 120})
    max_loop_count: int = Field(default=1, ge=1, le=100)
    stop_conditions: list[str] = Field(default_factory=lambda: ["max_loop_count"])
    checkpoint_required: bool = True
    approval_required: bool = True
    rollback_behavior: str = Field(default="restore_last_checkpoint", max_length=120)


class AutopilotRunStartRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    inputs: list[Any] = Field(default_factory=list)
    enabled_stages: dict[str, bool] = Field(default_factory=dict)
    scoring_method: Literal["pairwise", "tournament", "elo", "rubric"] = "pairwise"
    advanced_config: dict[str, Any] | None = None
    advanced_preset_id: str = Field(default="balanced", max_length=80)
    advanced_config_trust_origin: str = Field(default="user", max_length=80)


class AdvancedRunConfigValidateRequest(BaseModel):
    preset_id: str = Field(default="balanced", max_length=80)
    overrides: dict[str, Any] = Field(default_factory=dict)


class AutopilotCancelRequest(BaseModel):
    stop_reason: str = Field(default="cancelled by user", max_length=400)


class LiteratureReviewRunStartRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    question: str = Field(default="", max_length=2000)
    source_scope: dict[str, object] = Field(default_factory=lambda: {"kind": "all-project"})
    depth: Literal["quick", "standard", "deep"] = "standard"
    semantic_search: bool = False


class LiteratureReviewSaveRequestModel(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    destination: Literal["work/reviews", "knowledge/literature"]
    filename: str = Field(default="", max_length=240)


class IdeaRunStartRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    topic: str = Field(max_length=2_000)
    source_scope: str = Field(default="", max_length=2_000)
    constraints: str = Field(default="", max_length=4_000)
    novelty_target: str = Field(default="medium", max_length=40)
    enabled_stages: dict[str, bool] = Field(default_factory=dict)
    scoring_method: Literal["pairwise", "tournament", "elo", "rubric"] = "pairwise"


class IdeaPromoteRequest(BaseModel):
    project_id: str = Field(default="default", max_length=200)
    candidate_id: str = Field(max_length=200)
    target_kind: Literal["task", "note", "related_work"] = "task"


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


class McpServerRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    transport: str = Field(default="stdio", max_length=40)
    connection: dict = Field(default_factory=dict)
    auth_handle_ref: str | None = Field(default=None, max_length=400)
    connector: str | None = Field(default=None, max_length=80)


class McpServerEnableRequest(BaseModel):
    enabled: bool = True


class McpToolPermissionRequest(BaseModel):
    enabled: bool | None = None
    permission: Literal["allow", "deny"] | None = None
