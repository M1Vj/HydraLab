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
