from sqlalchemy import Column, Integer, BigInteger, String, Text, Float, Boolean, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class InputTypeEnum(str, enum.Enum):
    text = "text"
    image = "image"


class RiskLevelEnum(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class MatchResultEnum(str, enum.Enum):
    match = "match"
    no_match = "no_match"
    uncertain = "uncertain"


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), unique=True, nullable=False)
    input_type = Column(Enum(InputTypeEnum), nullable=False)
    risk_level = Column(Enum(RiskLevelEnum))
    result_json = Column(JSON)
    model_used = Column(String(100))
    processing_time_ms = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())

    # 관계
    message = relationship("Message", back_populates="analysis")
    images = relationship("AnalysisImage", back_populates="analysis", cascade="all, delete-orphan")
    keywords = relationship("AnalysisKeyword", back_populates="analysis", cascade="all, delete-orphan")
    image_matches = relationship("ImageMatch", back_populates="analysis", cascade="all, delete-orphan")
    claim_matches = relationship("ClaimMatch", back_populates="analysis", cascade="all, delete-orphan")


class AnalysisImage(Base):
    __tablename__ = "analysis_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    locarno_class = Column(String(20))
    created_at = Column(DateTime, server_default=func.now())

    # 관계
    analysis = relationship("Analysis", back_populates="images")


class AnalysisKeyword(Base):
    __tablename__ = "analysis_keywords"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False)
    keyword = Column(String(255), nullable=False)
    importance = Column(Float)

    # 관계
    analysis = relationship("Analysis", back_populates="keywords")


class ImageMatch(Base):
    __tablename__ = "image_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False)
    design_patent_id = Column(BigInteger, ForeignKey("design_patents.id"), nullable=True)  # 디자인 연동 전까지 nullable
    rag_score = Column(Float)
    model_score = Column(Float)
    is_similar = Column(Boolean)
    rank = Column(Integer)

    # 관계
    analysis = relationship("Analysis", back_populates="image_matches")
    # TODO: 디자인 팀 연동 후 활성화
    # design_patent = relationship("DesignPatent")


class ClaimMatch(Base):
    __tablename__ = "claim_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False)
    claim_id = Column(BigInteger, ForeignKey("claims.id"), nullable=True)  # RAG 연동 전까지 nullable
    rag_score = Column(Float)
    rerank_score = Column(Float)
    match_result = Column(Enum(MatchResultEnum))
    rank = Column(Integer)

    # 관계
    analysis = relationship("Analysis", back_populates="claim_matches")
    claim = relationship("Claim")
