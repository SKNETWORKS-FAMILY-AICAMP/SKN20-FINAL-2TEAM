from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

# SQLite 지원을 위한 connect_args
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """DB 세션 의존성"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """테이블 생성 — 기존 RAG 데이터 테이블(patents, claim_keywords, claim_components)은 건드리지 않음"""
    # 모든 모델 import (테이블 생성을 위해 필요)
    from app.models import user, chat, analysis, patent, design_session, project

    # 기존 RAG 데이터 테이블은 이미 RDS에 존재하므로 제외
    existing_rag_tables = {"patents", "claim_keywords", "claim_components"}
    tables_to_create = [
        t for t in Base.metadata.sorted_tables
        if t.name not in existing_rag_tables
    ]
    Base.metadata.create_all(bind=engine, tables=tables_to_create)

    # 기존 테이블에 새 컬럼이 없으면 추가
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if "design_sessions" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("design_sessions")}
        if "full_fto_reports_json" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE design_sessions ADD COLUMN full_fto_reports_json JSON"))
        if "individual_reports_json" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE design_sessions ADD COLUMN individual_reports_json JSON"))
