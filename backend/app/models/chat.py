from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class RoleEnum(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class MessageTypeEnum(str, enum.Enum):
    text = "text"
    image = "image"


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 관계
    user = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(Enum(RoleEnum), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(Enum(MessageTypeEnum), default=MessageTypeEnum.text)
    created_at = Column(DateTime, server_default=func.now())

    # 관계
    chat = relationship("Chat", back_populates="messages")
    analysis = relationship("Analysis", back_populates="message", uselist=False, cascade="all, delete-orphan")
