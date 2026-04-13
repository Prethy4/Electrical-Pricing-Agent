"""
LangChain-compatible chat memory backed by PostgreSQL (via our Message table).
Keeps the N most-recent messages in context to stay within token limits.
"""

from typing import List
from uuid import UUID

from langchain.schema import BaseMessage, HumanMessage, AIMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import MessageRepository


MAX_HISTORY_MESSAGES = 40  # max messages to load into context per turn


async def load_session_memory(
    session_id: UUID,
    db: AsyncSession,
) -> List[BaseMessage]:
    """Load recent chat history as LangChain BaseMessage objects."""
    repo = MessageRepository(db)
    messages = await repo.get_recent(session_id, limit=MAX_HISTORY_MESSAGES)

    lc_messages: List[BaseMessage] = []
    for msg in messages:
        if msg.role == "human":
            lc_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "ai":
            lc_messages.append(AIMessage(content=msg.content))
        # tool messages are intentionally omitted from top-level context
    return lc_messages


async def save_human_message(
    session_id: UUID,
    content: str,
    db: AsyncSession,
):
    repo = MessageRepository(db)
    return await repo.create(session_id=session_id, role="human", content=content)


async def save_ai_message(
    session_id: UUID,
    content: str,
    db: AsyncSession,
    tool_calls=None,
):
    repo = MessageRepository(db)
    return await repo.create(
        session_id=session_id,
        role="ai",
        content=content,
        tool_calls=tool_calls,
    )
