from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=800)


class SourceSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)


class WritingReviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class NoteCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    source_id: str | None = None


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    column: str = "To Do"
    detail: str = ""


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    column: str | None = None
    detail: str | None = None
    progress: int | None = Field(default=None, ge=0, le=100)


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


class ProviderSettingsRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    api_key_ref: str = Field(default="", max_length=300)
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
