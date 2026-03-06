"""디자인 세션 SQLAlchemy 모델.

S3 이미지 저장 + RDS 메타데이터 관리 + 멀티턴 대화 히스토리.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class DesignSessionStatus(str, enum.Enum):
    analyzing = "analyzing"
    waiting_selection = "waiting_selection"
    comparing = "comparing"
    completed = "completed"
    error = "error"


class ImageType(str, enum.Enum):
    user_upload = "user_upload"
    similar_design = "similar_design"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class DesignSession(Base):
    """디자인 분석 세션 메타데이터."""
    __tablename__ = "design_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(String(100), nullable=False, unique=True, index=True)
    user_id = Column(Integer, index=True)
    status = Column(
        Enum(DesignSessionStatus),
        default=DesignSessionStatus.analyzing
    )
    input_analysis = Column(Text)
    comparison_results_json = Column(JSON)
    selected_index = Column(Integer)
    final_report = Column(Text)
    full_fto_reports_json = Column(JSON)
    individual_reports_json = Column(JSON)  # {index: {result...}} 개별 분석 결과 누적
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # 관계
    images = relationship(
        "DesignSessionImage",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    messages = relationship(
        "DesignSessionMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="DesignSessionMessage.created_at"
    )


class DesignSessionImage(Base):
    """디자인 세션 이미지 (S3 URL 참조)."""
    __tablename__ = "design_session_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey("design_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    image_type = Column(Enum(ImageType), nullable=False)
    s3_key = Column(String(500), nullable=False)
    s3_url = Column(String(1000), nullable=False)
    original_filename = Column(String(255))
    file_size = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())

    # 관계
    session = relationship("DesignSession", back_populates="images")


class DesignSessionMessage(Base):
    """디자인 세션 멀티턴 대화 히스토리."""
    __tablename__ = "design_session_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey("design_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    role = Column(Enum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    image_id = Column(
        Integer,
        ForeignKey("design_session_images.id", ondelete="SET NULL")
    )
    created_at = Column(DateTime, server_default=func.now(), index=True)

    # 관계
    session = relationship("DesignSession", back_populates="messages")
