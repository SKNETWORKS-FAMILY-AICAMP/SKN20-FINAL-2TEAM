"""백엔드(FastAPI) 통합 어댑터.

하는 일:
    백엔드에서 RAG 검색을 간단히 호출할 수 있는 인터페이스를 제공합니다.
    - RAGSearchAdapter: pipeline.search()를 감싸는 래퍼
    - MySQLClaimsDB: backend MySQL에서 직접 청구항 조회 (rdb_filter.py 연동용)

사용법:
    # 독립 실행 (claims_db.json 사용)
    adapter = RAGSearchAdapter()
    results = adapter.search("헤스페리딘이 들어간 한방 액제", top_k=10)

    # 백엔드 MySQL 연동
    claims_db = MySQLClaimsDB(db_session)
    adapter = RAGSearchAdapter(claims_db=claims_db)
    results = adapter.search("...", top_k=10)

관계:
    - pipeline.py의 search()를 호출
    - rdb_filter.py의 ClaimsDBInterface를 MySQLClaimsDB가 구현
    - backend/app/services/search_service.py에서 import하여 사용
"""
from pathlib import Path

from . import config
from .pipeline import search
from .search.filter import ClaimsDBInterface, JsonClaimsDB


class RAGSearchAdapter:
    """백엔드에서 RAG 검색을 호출하기 위한 어댑터.

    Usage (Standalone):
        adapter = RAGSearchAdapter()
        results = adapter.search("헤스페리딘이 들어간 한방 액제", top_k=10)

    Usage (MySQL 연동):
        from rag.backend_adapter import RAGSearchAdapter, MySQLClaimsDB
        claims_db = MySQLClaimsDB(db_session)
        adapter = RAGSearchAdapter(claims_db=claims_db)
        results = adapter.search("...", top_k=10)
    """

    def __init__(self, claims_db: ClaimsDBInterface = None):
        self._claims_db = claims_db

    def search(self, query: str, top_k: int = None, **kwargs) -> list[dict]:
        """RAG 검색 실행."""
        return search(
            query=query,
            top_k=top_k,
            claims_db=self._claims_db,
            **kwargs,
        )


class MySQLClaimsDB:
    """MySQL 기반 ClaimsDB 구현.

    backend의 SQLAlchemy 세션을 주입받아 사용.
    실제 MySQL 스키마:
        - patents: id, application_num, register_num, title, register_status, ...
        - claims: id, patent_id (FK), claim_number, claim_text, claim_type, version_type, change_type
    """

    def __init__(self, db_session):
        self._session = db_session

    def _get_patent_id(self, apply_num: str) -> int | None:
        """application_num으로 patent_id 조회."""
        from sqlalchemy import text
        row = self._session.execute(
            text("SELECT id FROM patents WHERE application_num = :num"),
            {"num": apply_num},
        ).fetchone()
        return row[0] if row else None

    def get_patent(self, apply_num: str) -> dict | None:
        from sqlalchemy import text

        # 특허 기본 정보 조회
        row = self._session.execute(
            text("""
                SELECT id, application_num, register_num, title, register_status
                FROM patents WHERE application_num = :num
            """),
            {"num": apply_num},
        ).fetchone()

        if not row:
            return None

        patent_id = row[0]

        # 청구항 조회 (patent_id로 JOIN)
        last_claims = self._session.execute(
            text("""
                SELECT claim_number, claim_type, change_type, claim_text
                FROM claims
                WHERE patent_id = :pid AND version_type = 'last'
                ORDER BY claim_number
            """),
            {"pid": patent_id},
        ).fetchall()

        first_claims = self._session.execute(
            text("""
                SELECT claim_number, claim_type, claim_text
                FROM claims
                WHERE patent_id = :pid AND version_type = 'first'
                ORDER BY claim_number
            """),
            {"pid": patent_id},
        ).fetchall()

        return {
            "metadata": {
                "apply_num": row[1] or "",           # application_num
                "regit_num": row[2] or "",           # register_num
                "register_status": row[4] or "",     # register_status
                "invention_title": row[3] or "",     # title
            },
            "last_claims": [
                {
                    "claim_number": c[0],    # claim_number
                    "claim_type": c[1],      # claim_type
                    "change_type": c[2],     # change_type
                    "text": c[3],            # claim_text
                }
                for c in last_claims
            ],
            "first_claims": [
                {
                    "claim_number": c[0],    # claim_number
                    "claim_type": c[1],      # claim_type
                    "text": c[2],            # claim_text
                }
                for c in first_claims
            ],
            "estoppel_claim_numbers": [
                c[0] for c in last_claims    # claim_number
                if c[2] == "삭제"            # change_type
            ],
        }

    def is_registered(self, apply_num: str) -> bool:
        from sqlalchemy import text
        row = self._session.execute(
            text("SELECT register_status FROM patents WHERE application_num = :num"),
            {"num": apply_num},
        ).fetchone()
        return row is not None and row[0] == "등록"

    def get_estoppel_claims(self, apply_num: str) -> list[int]:
        from sqlalchemy import text
        patent_id = self._get_patent_id(apply_num)
        if not patent_id:
            return []
        rows = self._session.execute(
            text("""
                SELECT claim_number FROM claims
                WHERE patent_id = :pid
                  AND version_type = 'last'
                  AND change_type = '삭제'
            """),
            {"pid": patent_id},
        ).fetchall()
        return [r[0] for r in rows]
