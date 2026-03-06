from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class ProjectType(str, enum.Enum):
    patent = "patent"
    design = "design"


class Project(Base):
    """사용자 프로젝트 (특허/디자인 세션 그룹)."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    type = Column(Enum(ProjectType), nullable=False, default=ProjectType.patent)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User")
    sessions = relationship("ProjectSession", back_populates="project", cascade="all, delete-orphan")


class ProjectSession(Base):
    """프로젝트에 포함된 세션 매핑."""
    __tablename__ = "project_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    chat_id = Column(Integer, index=True)
    thread_id = Column(String(100), index=True)
    added_at = Column(DateTime, server_default=func.now())

    project = relationship("Project", back_populates="sessions")
