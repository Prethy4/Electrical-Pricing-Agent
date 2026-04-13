from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID


# ── Session ──────────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    title: Optional[str] = None

class SessionResponse(BaseModel):
    id: UUID
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    metadata: dict = Field(default_factory=dict, alias="metadata_")

    class Config:
        from_attributes = True
        populate_by_name = True


# ── Message ───────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    tool_calls: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10_000)
    session_id: Optional[UUID] = None   # if None → create new session

class ChatResponse(BaseModel):
    session_id: UUID
    message: MessageResponse
    sources: Optional[List[dict]] = None  # doc sources used, if any


# ── File Upload ───────────────────────────────────────────────────────────────

class FileUploadResponse(BaseModel):
    id: UUID
    session_id: UUID
    filename: str
    file_type: str
    file_size: int
    processed: bool
    chunk_count: int
    created_at: datetime

    class Config:
        from_attributes = True


# ── History ───────────────────────────────────────────────────────────────────

class SessionHistoryResponse(BaseModel):
    session: SessionResponse
    messages: List[MessageResponse]
    files: List[FileUploadResponse]
