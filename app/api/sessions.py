from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from app.db.database import get_db
from app.db.repositories import SessionRepository
from app.models.schemas import SessionCreate, SessionResponse, SessionHistoryResponse, MessageResponse, FileUploadResponse

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Explicitly create a new chat session."""
    repo = SessionRepository(db)
    session = await repo.create(title=body.title)
    return SessionResponse.model_validate(session)


@router.get("", response_model=List[SessionResponse])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    """List all sessions, newest first."""
    repo = SessionRepository(db)
    sessions = await repo.list_all()
    return [SessionResponse.model_validate(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionHistoryResponse)
async def get_session(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """Retrieve a session with its full message history and file list."""
    repo = SessionRepository(db)
    session = await repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionHistoryResponse(
        session=SessionResponse.model_validate(session),
        messages=[MessageResponse.model_validate(m) for m in session.messages],
        files=[FileUploadResponse.model_validate(f) for f in session.uploaded_files],
    )


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete a session and all its messages."""
    repo = SessionRepository(db)
    deleted = await repo.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
