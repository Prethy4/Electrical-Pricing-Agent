from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from app.models.db_models import Session, Message, UploadedFile
from typing import List, Optional
from uuid import UUID
import uuid


class SessionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, title: Optional[str] = None) -> Session:
        session = Session(title=title)
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def get(self, session_id: UUID) -> Optional[Session]:
        result = await self.db.execute(
            select(Session)
            .where(Session.id == session_id)
            .options(
                selectinload(Session.messages),
                selectinload(Session.uploaded_files),
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> List[Session]:
        result = await self.db.execute(
            select(Session).order_by(Session.updated_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, session_id: UUID) -> bool:
        result = await self.db.execute(
            delete(Session).where(Session.id == session_id)
        )
        return result.rowcount > 0


class MessageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        session_id: UUID,
        role: str,
        content: str,
        tool_calls=None,
    ) -> Message:
        msg = Message(
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
        )
        self.db.add(msg)
        await self.db.flush()
        await self.db.refresh(msg)
        return msg

    async def get_session_messages(self, session_id: UUID) -> List[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_recent(self, session_id: UUID, limit: int = 20) -> List[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))


class FileRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        session_id: UUID,
        filename: str,
        file_type: str,
        file_path: str,
        file_size: int,
    ) -> UploadedFile:
        f = UploadedFile(
            session_id=session_id,
            filename=filename,
            file_type=file_type,
            file_path=file_path,
            file_size=file_size,
        )
        self.db.add(f)
        await self.db.flush()
        await self.db.refresh(f)
        return f

    async def mark_processed(self, file_id: UUID, chunk_count: int) -> None:
        result = await self.db.execute(
            select(UploadedFile).where(UploadedFile.id == file_id)
        )
        f = result.scalar_one_or_none()
        if f:
            f.processed = True
            f.chunk_count = chunk_count

    async def get_session_files(self, session_id: UUID) -> List[UploadedFile]:
        result = await self.db.execute(
            select(UploadedFile).where(UploadedFile.session_id == session_id)
        )
        return list(result.scalars().all())
