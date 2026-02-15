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
from . import config
from .pipeline import search
from .search.filter import ClaimsDBInterface


# ══════════════════════════════════════════════════════
# RAG 검색 어댑터 (백엔드 → pipeline.search 래퍼)
# ══════════════════════════════════════════════════════

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
        # claims_db가 None이면 기본 SQLiteClaimsDB 사용 (pipeline 내부 처리)
        self._claims_db = claims_db

    def search(self, query: str, top_k: int = None, **kwargs) -> list[dict]:
        """RAG 검색 실행. pipeline.search()에 위임."""
        return search(
            query=query,
            top_k=top_k,
            claims_db=self._claims_db,
            **kwargs,
        )



# ══════════════════════════════════════════════════════
# MySQL 기반 ClaimsDB (백엔드 SQLAlchemy 세션 사용)
# ══════════════════════════════════════════════════════

class MySQLClaimsDB:
    """MySQL 기반 ClaimsDB 구현.

    backend의 SQLAlchemy 세션을 주입받아 사용.
    """

    def __init__(self, db_session):
        # SQLAlchemy 세션을 주입받아 DB 쿼리에 사용
        self._session = db_session

    def get_patent(self, apply_num: str) -> dict | None:
        """출원번호로 특허 정보(메타+청구항+금반언) 조회."""
        from sqlalchemy import text

        # 특허 기본 정보 조회
        row = self._session.execute(
            text("SELECT * FROM patents WHERE application_number = :num"),
            {"num": apply_num},
        ).fetchone()

        if not row:
            return None

        # 최종 버전 청구항 조회 (등록 시점 기준)
        last_claims = self._session.execute(
            text("""
                SELECT claim_number, claim_type, change_type, claim_text
                FROM claims
                WHERE application_number = :num AND version_type = 'last'
                ORDER BY claim_number
            """),
            {"num": apply_num},
        ).fetchall()

        # 최초 출원 버전 청구항 조회 (금반언 비교용)
        first_claims = self._session.execute(
            text("""
                SELECT claim_number, claim_type, claim_text
                FROM claims
                WHERE application_number = :num AND version_type = 'first'
                ORDER BY claim_number
            """),
            {"num": apply_num},
        ).fetchall()

        return {
            "metadata": {
                "apply_num": apply_num,
                "regit_num": row.register_number if hasattr(row, 'register_number') else "",
                "register_status": row.register_status if hasattr(row, 'register_status') else "",
                "invention_title": row.invention_title if hasattr(row, 'invention_title') else "",
            },
            # 최종 청구항 목록 (change_type 포함: 삭제/변경/유지)
            "last_claims": [
                {
                    "claim_number": c.claim_number,
                    "claim_type": c.claim_type,
                    "change_type": c.change_type,
                    "text": c.claim_text,
                }
                for c in last_claims
            ],
            # 최초 출원 청구항 (금반언 대비표 작성용)
            "first_claims": [
                {
                    "claim_number": c.claim_number,
                    "claim_type": c.claim_type,
                    "text": c.claim_text,
                }
                for c in first_claims
            ],
            # 금반언 대상 청구항 번호 (삭제된 청구항 = 침해 주장 불가)
            "estoppel_claim_numbers": [
                c.claim_number for c in last_claims
                if c.change_type == "삭제"
            ],
        }

    def is_registered(self, apply_num: str) -> bool:
        """특허 등록 여부 확인. 미등록/소멸 특허는 침해 판단 대상에서 제외."""
        from sqlalchemy import text
        row = self._session.execute(
            text("SELECT register_status FROM patents WHERE application_number = :num"),
            {"num": apply_num},
        ).fetchone()
        return row is not None and row.register_status == "등록"

    def get_estoppel_claims(self, apply_num: str) -> list[int]:
        """금반언 대상 청구항 번호 목록 조회. 삭제된 청구항 = 출원인이 포기한 권리."""
        from sqlalchemy import text
        rows = self._session.execute(
            text("""
                SELECT claim_number FROM claims
                WHERE application_number = :num
                  AND version_type = 'last'
                  AND change_type = '삭제'
            """),
            {"num": apply_num},
        ).fetchall()
        return [r.claim_number for r in rows]
