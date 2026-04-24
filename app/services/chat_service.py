"""
ChatService: top-level orchestrator for a single chat turn.
  1. Ensure session exists in DB
  2. Load memory (recent messages)
  3. Get retriever if files exist
  4. Run agent graph
  5. Persist human + AI messages
  6. Return response
"""

from uuid import UUID
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import SessionRepository, MessageRepository
from app.services.memory_service import load_session_memory, save_human_message, save_ai_message
from app.services.file_service import get_retriever
from app.agents.graph import run_agent
from app.models.db_models import Message, Session


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.session_repo = SessionRepository(db)
        self.message_repo = MessageRepository(db)

    async def get_or_create_session(
        self,
        session_id: Optional[UUID],
        first_message: str,
    ) -> Session:
        if session_id:
            try:
                uid = UUID(str(session_id))
                session = await self.session_repo.get(uid)
                if session:
                    return session
            except (ValueError, AttributeError):
                pass

        # Auto-title the session from the first message
        title = first_message[:60] + ("…" if len(first_message) > 60 else "")
        return await self.session_repo.create(title=title)

    async def chat(
        self,
        user_message: str,
        session_id: Optional[UUID] = None,
    ) -> Tuple[Message, UUID]:
        """
        Process one user message. Returns (ai_message_db_obj, session_id).
        """
        session = await self.get_or_create_session(session_id, user_message)
        sid = session.id

        # Load history
        history = await load_session_memory(sid, self.db)

        # Retriever (None if no files)
        retriever = get_retriever(sid)

        # Run agent
        ai_text, tool_calls = await run_agent(
            user_message=user_message,
            history=history,
            retriever=retriever,
            session_id=sid,
        )

        # Persist messages
        await save_human_message(sid, user_message, self.db)
        ai_msg = await save_ai_message(sid, ai_text, self.db, tool_calls=tool_calls)

        return ai_msg, sid
