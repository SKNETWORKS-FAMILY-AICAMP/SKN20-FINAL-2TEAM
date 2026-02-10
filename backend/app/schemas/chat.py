from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from enum import Enum


class RoleEnum(str, Enum):
    user = "user"
    assistant = "assistant"


class MessageTypeEnum(str, Enum):
    text = "text"
    image = "image"


class MessageCreate(BaseModel):
    content: str
    message_type: MessageTypeEnum = MessageTypeEnum.text


class MessageResponse(BaseModel):
    id: int
    role: RoleEnum
    content: str
    message_type: MessageTypeEnum
    created_at: datetime

    class Config:
        from_attributes = True


class ChatCreate(BaseModel):
    title: Optional[str] = None


class ChatResponse(BaseModel):
    id: int
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = []

    class Config:
        from_attributes = True


class ChatListResponse(BaseModel):
    id: int
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    class Config:
        from_attributes = True
