"""
하이브리드 검색 서비스
- RDB 검색 (키워드 기반)
- ChromaDB 검색 (벡터 기반) - RAG 팀원 연동
- 결과 병합 및 필터링
"""
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func

from app.models.patent import Patent, Claim, ClaimElement, PatentIPC


class SearchService:
    """하이브리드 검색 서비스"""

    def __init__(self, db: Session):
        self.db = db

    def search_by_keywords(
        self,
        keywords: list[str],
        limit: int = 20,
        ipc_filter: Optional[str] = None,
        only_registered: bool = True
    ) -> list[dict]:
        """
        RDB 키워드 검색
        - claim_elements 테이블에서 키워드 매칭
        - 금반언 적용: last 버전의 삭제되지 않은 청구항만 반환

        Args:
            keywords: 검색할 키워드 리스트
            limit: 최대 결과 수
            ipc_filter: IPC 분류코드 필터 (선택)
            only_registered: 등록된 특허만 검색할지 여부

        Returns:
            매칭된 청구항 정보 리스트
        """
        if not keywords:
            return []

        # 키워드 패턴 생성 (LIKE 검색용)
        patterns = [f"%{kw}%" for kw in keywords]

        # 기본 쿼리: claim_elements → claims → patents
        query = (
            self.db.query(
                Claim.id.label('claim_id'),
                Claim.claim_number,
                Claim.claim_text,
                Claim.claim_type,
                Claim.change_type,
                Patent.id.label('patent_id'),
                Patent.application_num,
                Patent.register_num,
                Patent.title,
                Patent.applicant,
                Patent.register_status,
                func.count(ClaimElement.id).label('match_count')
            )
            .join(Claim, ClaimElement.claim_id == Claim.id)
            .join(Patent, Claim.patent_id == Patent.id)
            .filter(
                # 금반언: last 버전만, 삭제되지 않은 것만
                Claim.version_type == 'last',
                or_(Claim.change_type != '삭제', Claim.change_type.is_(None)),
                # 키워드 매칭
                or_(
                    *[ClaimElement.element_name.like(p) for p in patterns],
                    *[ClaimElement.element_name_eng.like(p) for p in patterns]
                )
            )
        )

        # 등록된 특허만 필터
        if only_registered:
            query = query.filter(Patent.register_status == '등록')

        # IPC 필터 적용
        if ipc_filter:
            query = query.join(PatentIPC, Patent.id == PatentIPC.patent_id)
            query = query.filter(PatentIPC.ipc_code.like(f"{ipc_filter}%"))

        # 그룹화 및 정렬
        results = (
            query
            .group_by(Claim.id, Patent.id)
            .order_by(func.count(ClaimElement.id).desc())
            .limit(limit)
            .all()
        )

        return [
            {
                'claim_id': r.claim_id,
                'claim_number': r.claim_number,
                'claim_text': r.claim_text,
                'claim_type': r.claim_type,
                'patent_id': r.patent_id,
                'application_num': r.application_num,
                'register_num': r.register_num,
                'title': r.title,
                'applicant': r.applicant,
                'match_count': r.match_count,
                'source': 'rdb'
            }
            for r in results
        ]

    def search_fulltext(
        self,
        query_text: str,
        limit: int = 20
    ) -> list[dict]:
        """
        전문 검색 (FULLTEXT)
        - claim_elements의 element_name 필드에 FULLTEXT 인덱스 사용

        Args:
            query_text: 검색어
            limit: 최대 결과 수

        Returns:
            매칭된 청구항 정보 리스트
        """
        # MySQL FULLTEXT 검색 (MATCH AGAINST)
        sql = """
            SELECT
                c.id as claim_id,
                c.claim_number,
                c.claim_text,
                c.claim_type,
                p.id as patent_id,
                p.application_num,
                p.register_num,
                p.title,
                p.applicant,
                MATCH(ce.element_name) AGAINST(:query IN NATURAL LANGUAGE MODE) as relevance
            FROM claim_elements ce
            JOIN claims c ON ce.claim_id = c.id
            JOIN patents p ON c.patent_id = p.id
            WHERE c.version_type = 'last'
              AND (c.change_type != '삭제' OR c.change_type IS NULL)
              AND p.register_status = '등록'
              AND MATCH(ce.element_name) AGAINST(:query IN NATURAL LANGUAGE MODE)
            GROUP BY c.id, p.id
            ORDER BY relevance DESC
            LIMIT :limit
        """

        from sqlalchemy import text
        results = self.db.execute(
            text(sql),
            {'query': query_text, 'limit': limit}
        ).fetchall()

        return [
            {
                'claim_id': r.claim_id,
                'claim_number': r.claim_number,
                'claim_text': r.claim_text,
                'claim_type': r.claim_type,
                'patent_id': r.patent_id,
                'application_num': r.application_num,
                'register_num': r.register_num,
                'title': r.title,
                'applicant': r.applicant,
                'relevance': float(r.relevance),
                'source': 'fulltext'
            }
            for r in results
        ]

    def get_estoppel_claims(self, patent_id: int) -> list[dict]:
        """
        금반언 청구항 조회
        - 출원 시에는 있었으나 등록 시 삭제된 청구항

        Args:
            patent_id: 특허 ID

        Returns:
            삭제된 청구항 리스트 (금반언 적용 대상)
        """
        # first 버전에 있고, last 버전에서 삭제된 청구항
        results = (
            self.db.query(Claim)
            .filter(
                Claim.patent_id == patent_id,
                Claim.version_type == 'last',
                Claim.change_type == '삭제'
            )
            .all()
        )

        return [
            {
                'claim_number': r.claim_number,
                'original_text': self._get_first_version_text(patent_id, r.claim_number),
                'status': '삭제 (금반언 적용)'
            }
            for r in results
        ]

    def _get_first_version_text(self, patent_id: int, claim_number: int) -> str:
        """출원 시 청구항 텍스트 조회"""
        result = (
            self.db.query(Claim.claim_text)
            .filter(
                Claim.patent_id == patent_id,
                Claim.claim_number == claim_number,
                Claim.version_type == 'first'
            )
            .first()
        )
        return result.claim_text if result else ''

    def merge_results(
        self,
        rdb_results: list[dict],
        rag_results: list[dict],
        top_n: int = 10
    ) -> list[dict]:
        """
        RDB 검색 결과와 RAG 검색 결과 병합

        Args:
            rdb_results: RDB 키워드 검색 결과
            rag_results: ChromaDB 벡터 검색 결과
            top_n: 최종 반환할 결과 수

        Returns:
            병합된 결과 (교집합 우선)
        """
        # claim_id를 키로 결과 정리
        rdb_claims = {r['claim_id']: r for r in rdb_results}
        rag_claims = {r['claim_id']: r for r in rag_results}

        merged = []

        # 1. 교집합 (양쪽 모두에 있는 것) - 최우선
        intersection = set(rdb_claims.keys()) & set(rag_claims.keys())
        for claim_id in intersection:
            result = rdb_claims[claim_id].copy()
            result['source'] = 'both'
            result['rag_score'] = rag_claims[claim_id].get('score', 0)
            merged.append(result)

        # 2. RAG에만 있는 것 (의미적 유사)
        rag_only = set(rag_claims.keys()) - intersection
        for claim_id in rag_only:
            result = rag_claims[claim_id].copy()
            merged.append(result)

        # 3. RDB에만 있는 것 (키워드 정확 매칭)
        rdb_only = set(rdb_claims.keys()) - intersection
        for claim_id in rdb_only:
            result = rdb_claims[claim_id].copy()
            merged.append(result)

        # 정렬: 교집합 > match_count/score 순
        def sort_key(x):
            source_priority = {'both': 0, 'rag': 1, 'rdb': 2, 'fulltext': 2}
            return (
                source_priority.get(x.get('source', 'rdb'), 3),
                -x.get('match_count', 0),
                -x.get('rag_score', 0)
            )

        merged.sort(key=sort_key)

        return merged[:top_n]


def extract_keywords(text: str) -> list[str]:
    """
    사용자 입력에서 키워드 추출 (간단한 규칙 기반)

    Args:
        text: 사용자 입력 텍스트

    Returns:
        추출된 키워드 리스트
    """
    import re

    # 불용어
    stopwords = {
        '있는', '하는', '하고', '했어', '만들', '개발', '출시', '예정',
        '제품', '기획', '중이야', '거야', '했어', '있어', '이야',
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would'
    }

    # 한글, 영문 단어 추출
    words = re.findall(r'[가-힣]{2,}|[A-Za-z]{3,}[-A-Za-z0-9]*', text)

    # 불용어 제거 및 중복 제거
    keywords = []
    seen = set()
    for word in words:
        lower_word = word.lower()
        if lower_word not in stopwords and lower_word not in seen:
            keywords.append(word)
            seen.add(lower_word)

    return keywords
