from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.chat import Chat, Message, RoleEnum, MessageTypeEnum


class ChatService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_chats(self, user_id: int) -> List[dict]:
        """사용자의 채팅 목록 조회"""
        chats = (
            self.db.query(
                Chat,
                func.count(Message.id).label("message_count")
            )
            .outerjoin(Message)
            .filter(Chat.user_id == user_id)
            .group_by(Chat.id)
            .order_by(Chat.updated_at.desc())
            .all()
        )

        result = []
        for chat, message_count in chats:
            result.append({
                "id": chat.id,
                "title": chat.title,
                "created_at": chat.created_at,
                "updated_at": chat.updated_at,
                "message_count": message_count
            })

        return result

    def create_chat(self, user_id: int, title: Optional[str] = None) -> Chat:
        """새 채팅 생성"""
        chat = Chat(
            user_id=user_id,
            title=title or "새 대화"
        )

        self.db.add(chat)
        self.db.commit()
        self.db.refresh(chat)

        return chat

    def get_chat(self, chat_id: int, user_id: int) -> Optional[Chat]:
        """채팅 조회 (소유권 확인)"""
        return (
            self.db.query(Chat)
            .filter(Chat.id == chat_id, Chat.user_id == user_id)
            .first()
        )

    def delete_chat(self, chat_id: int, user_id: int) -> bool:
        """채팅 삭제"""
        chat = self.get_chat(chat_id, user_id)

        if not chat:
            return False

        self.db.delete(chat)
        self.db.commit()

        return True

    def add_message(
        self,
        chat_id: int,
        role: str,
        content: str,
        message_type: str = "text"
    ) -> Message:
        """메시지 추가"""
        message = Message(
            chat_id=chat_id,
            role=RoleEnum(role),
            content=content,
            message_type=MessageTypeEnum(message_type)
        )

        self.db.add(message)

        # 채팅 updated_at 갱신
        chat = self.db.query(Chat).filter(Chat.id == chat_id).first()
        if chat:
            chat.updated_at = func.now()

        self.db.commit()
        self.db.refresh(message)

        return message

    def get_messages(self, chat_id: int) -> List[Message]:
        """채팅의 모든 메시지 조회"""
        return (
            self.db.query(Message)
            .filter(Message.chat_id == chat_id)
            .order_by(Message.created_at.asc())
            .all()
        )

    def update_chat_title(self, chat_id: int, user_id: int, title: str) -> Optional[Chat]:
        """채팅 제목 수정"""
        chat = self.get_chat(chat_id, user_id)

        if not chat:
            return None

        chat.title = title
        self.db.commit()
        self.db.refresh(chat)

        return chat
