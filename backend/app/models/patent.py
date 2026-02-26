from sqlalchemy import Column, String, Text, Date, DateTime
from sqlalchemy.sql import func

from app.database import Base


class Patent(Base):
    """특허 기본 정보 — RDS patents 테이블 매핑"""
    __tablename__ = "patents"
    __table_args__ = {'keep_existing': True}

    apply_num = Column(String(50), primary_key=True, comment='출원번호')
    invention_title = Column(String(500), comment='발명명')
    invention_title_eng = Column(String(500), comment='영문 발명명')
    abstract = Column(Text, comment='초록')
    applicant = Column(String(255), comment='출원인')
    register_status = Column(String(20), comment='등록상태')
    regit_num = Column(String(50), comment='등록번호')
    application_date = Column(String(20), comment='출원일')
    open_date = Column(String(20), comment='공개일')
    register_date = Column(String(20), comment='등록일')
    claim_pub = Column(Text, comment='공개 청구항 텍스트')
    claim_regit = Column(Text, comment='등록 청구항 텍스트')
    chunk_ids = Column(Text, comment='ChromaDB 청크 ID 목록 (JSON)')
