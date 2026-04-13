import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey,
    JSON, Integer, Boolean, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


class Session(Base):
    """A chat session (conversation thread)."""
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    metadata_ = Column("metadata", JSON, default=dict)

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan", order_by="Message.created_at")
    uploaded_files = relationship("UploadedFile", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    """A single message in a chat session."""
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False)          # "human" | "ai" | "tool"
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True)           # serialized tool call info
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("Session", back_populates="messages")


class UploadedFile(Base):
    """File uploaded by a user in a session."""
    __tablename__ = "uploaded_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    file_type = Column(String(50), nullable=False)     # "pdf" | "csv"
    file_path = Column(String(1000), nullable=False)
    file_size = Column(Integer, nullable=False)
    processed = Column(Boolean, default=False)
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("Session", back_populates="uploaded_files")
