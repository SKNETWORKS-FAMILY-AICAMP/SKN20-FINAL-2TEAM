from sqlalchemy import Column, Integer, BigInteger, String, Text, Date, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class ClaimTypeEnum(str, enum.Enum):
    independent = "independent"
    dependent = "dependent"


class VersionTypeEnum(str, enum.Enum):
    first = "first"   # 출원 시 청구항
    last = "last"     # 등록 시 청구항


# ==================== 일반 특허 ====================

class Patent(Base):
    """특허 기본 정보"""
    __tablename__ = "patents"
    __table_args__ = {'extend_existing': True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    application_num = Column(String(50), unique=True, nullable=False, comment='출원번호')
    register_num = Column(String(50), index=True, comment='등록번호')
    open_num = Column(String(50), comment='공개번호')
    title = Column(String(500), nullable=False, comment='발명명')
    title_eng = Column(String(500), comment='영문 발명명')
    abstract = Column(Text, comment='초록')
    applicant = Column(String(255), comment='출원인')
    applicant_eng = Column(String(255), comment='출원인(영문)')
    register_status = Column(String(20), index=True, comment='등록상태')
    application_date = Column(Date, comment='출원일')
    register_date = Column(Date, comment='등록일')
    open_date = Column(Date, comment='공개일')
    created_at = Column(DateTime, server_default=func.now())

    # 관계
    ipc_codes = relationship("PatentIPC", back_populates="patent", cascade="all, delete-orphan")
    claims = relationship("Claim", back_populates="patent", cascade="all, delete-orphan")


class PatentIPC(Base):
    """IPC 분류코드 (1:N)"""
    __tablename__ = "patent_ipc"
    __table_args__ = {'extend_existing': True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    patent_id = Column(BigInteger, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False)
    ipc_code = Column(String(50), nullable=False, index=True, comment='IPC 분류코드')
    ipc_date = Column(String(20), comment='IPC 날짜')

    # 관계
    patent = relationship("Patent", back_populates="ipc_codes")


class Claim(Base):
    """청구항 (금반언 지원: first/last 버전)"""
    __tablename__ = "claims"
    __table_args__ = {'extend_existing': True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    patent_id = Column(BigInteger, ForeignKey("patents.id", ondelete="CASCADE"), nullable=False)
    claim_number = Column(Integer, nullable=False, comment='청구항 번호')
    claim_text = Column(Text, nullable=False, comment='청구항 텍스트')
    claim_type = Column(String(20), default='independent', comment='independent/dependent')
    version_type = Column(String(10), nullable=False, comment='first(출원) / last(등록)')
    change_type = Column(String(10), comment='신규/수정/삭제')
    refers_to = Column(JSON, comment='종속항 참조 번호 배열')
    created_at = Column(DateTime, server_default=func.now())

    # 관계
    patent = relationship("Patent", back_populates="claims")
    elements = relationship("ClaimElement", back_populates="claim", cascade="all, delete-orphan")


class ClaimElement(Base):
    """청구항 핵심 요소 (RDB 키워드 검색용)"""
    __tablename__ = "claim_elements"
    __table_args__ = {'extend_existing': True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    claim_id = Column(BigInteger, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    element_type = Column(String(50), comment='성분/방법/구조/제품유형')
    element_name = Column(String(200), nullable=False, index=True, comment='요소명 (정규화)')
    element_name_eng = Column(String(200), index=True, comment='영문명')
    synonyms = Column(JSON, comment='동의어/약어 배열')

    # 관계
    claim = relationship("Claim", back_populates="elements")


# ==================== 디자인 특허 (이미지용) ====================

class DesignPatent(Base):
    """디자인 특허"""
    __tablename__ = "design_patents"
    __table_args__ = {'extend_existing': True}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    regit_num = Column(String(50), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    locarno_class = Column(String(20), index=True)
    applicant = Column(String(255))
    image_path = Column(String(500))
    filing_date = Column(Date)
    created_at = Column(DateTime, server_default=func.now())
