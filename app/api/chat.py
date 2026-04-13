from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.schemas import ChatRequest, ChatResponse, MessageResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message to the agent.

    - Provide `session_id` to continue an existing conversation.
    - Omit `session_id` (or pass null) to start a new session automatically.
    """
    service = ChatService(db)
    try:
        ai_msg, session_id = await service.chat(
            user_message=req.message,
            session_id=req.session_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return ChatResponse(
        session_id=session_id,
        message=MessageResponse.model_validate(ai_msg),
    )
