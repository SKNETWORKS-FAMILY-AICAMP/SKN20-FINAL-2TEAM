from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, Enum, Integer, LargeBinary
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base
from app.config import settings

# PostgreSQL + pgvector 사용 시 Vector 타입, 그 외에는 LargeBinary
try:
    if "postgresql" in settings.DATABASE_URL:
        from pgvector.sqlalchemy import Vector
    else:
        Vector = lambda dim: LargeBinary  # SQLite 등에서는 LargeBinary 사용
except ImportError:
    Vector = lambda dim: LargeBinary


class ClaimTypeEnum(str, enum.Enum):
    independent = "independent"
    dependent = "dependent"


# ==================== 디자인 특허 (이미지용) ====================

class DesignPatent(Base):
    __tablename__ = "design_patents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    regit_num = Column(String(50), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    locarno_class = Column(String(20), index=True)
    applicant = Column(String(255))
    image_path = Column(String(500))
    filing_date = Column(Date)
    created_at = Column(DateTime, server_default=func.now())

    # 관계
    embedding = relationship("DesignEmbedding", back_populates="design_patent", uselist=False, cascade="all, delete-orphan")


class DesignEmbedding(Base):
    __tablename__ = "design_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    design_patent_id = Column(Integer, ForeignKey("design_patents.id", ondelete="CASCADE"), unique=True, nullable=False)
    embedding = Column(Vector(512))  # CLIP 임베딩
    model_name = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())

    # 관계
    design_patent = relationship("DesignPatent", back_populates="embedding")


# ==================== 일반 특허 (텍스트용) ====================

class Patent(Base):
    __tablename__ = "patents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    regit_num = Column(String(50), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    applicant = Column(String(255))
    ipc_code = Column(String(50))
    abstract = Column(Text)
    filing_date = Column(Date)
    created_at = Column(DateTime, server_default=func.now())

    # 관계
    claims = relationship("Claim", back_populates="patent", cascade="all, delete-orphan")


class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patent_id = Column(Integer, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False)
    claim_number = Column(Integer, nullable=False)
    claim_text = Column(Text, nullable=False)
    claim_type = Column(Enum(ClaimTypeEnum), default=ClaimTypeEnum.independent)
    created_at = Column(DateTime, server_default=func.now())

    # 관계
    patent = relationship("Patent", back_populates="claims")
    embedding = relationship("ClaimEmbedding", back_populates="claim", uselist=False, cascade="all, delete-orphan")


class ClaimEmbedding(Base):
    __tablename__ = "claim_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(Integer, ForeignKey("claims.id", ondelete="CASCADE"), unique=True, nullable=False)
    embedding = Column(Vector(1536))  # OpenAI ada-002
    model_name = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())

    # 관계
    claim = relationship("Claim", back_populates="embedding")
