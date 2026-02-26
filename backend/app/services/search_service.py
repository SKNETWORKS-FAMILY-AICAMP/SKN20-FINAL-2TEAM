"""
하이브리드 검색 서비스
- RDB 검색 (claim_keywords 테이블 기반)
- 결과 병합 및 필터링
"""
import re
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text


class SearchService:
    """하이브리드 검색 서비스 — RDS claim_keywords/patents 테이블 사용"""

    def __init__(self, db: Session):
        self.db = db

    def search_by_keywords(
        self,
        keywords: list[str],
        limit: int = 20,
        ipc_filter: Optional[str] = None,
        only_registered: bool = True
    ) -> list[dict]:
        """RDB 키워드 검색 — claim_keywords 테이블에서 매칭."""
        if not keywords:
            return []

        placeholders = ", ".join([":kw{}".format(i) for i in range(len(keywords))])
        params = {f"kw{i}": kw for i, kw in enumerate(keywords)}
        params["limit"] = limit

        sql = f"""
            SELECT ck.patent_id, ck.chunk_id, COUNT(*) as match_count,
                   p.invention_title, p.applicant, p.register_status, p.regit_num
            FROM claim_keywords ck
            LEFT JOIN patents p ON ck.patent_id = p.apply_num
            WHERE ck.keyword IN ({placeholders})
        """
        if only_registered:
            sql += " AND (p.register_status = '등록' OR p.register_status = '공개')"
        sql += " GROUP BY ck.patent_id, ck.chunk_id ORDER BY match_count DESC LIMIT :limit"

        results = self.db.execute(text(sql), params).fetchall()

        return [
            {
                'patent_id': r[0],
                'chunk_id': r[1],
                'match_count': r[2],
                'title': r[3] or '',
                'applicant': r[4] or '',
                'register_status': r[5] or '',
                'register_num': r[6] or '',
                'source': 'rdb'
            }
            for r in results
        ]

    def search_fulltext(self, query_text: str, limit: int = 20) -> list[dict]:
        """전문 검색 (LIKE 기반 폴백)."""
        sql = """
            SELECT apply_num, invention_title, applicant, register_status, regit_num
            FROM patents
            WHERE invention_title LIKE :query OR claim_regit LIKE :query
            LIMIT :limit
        """
        results = self.db.execute(
            text(sql),
            {'query': f'%{query_text}%', 'limit': limit}
        ).fetchall()

        return [
            {
                'patent_id': r[0],
                'title': r[1] or '',
                'applicant': r[2] or '',
                'register_status': r[3] or '',
                'register_num': r[4] or '',
                'source': 'fulltext'
            }
            for r in results
        ]

    def get_estoppel_claims(self, patent_id: str) -> list[dict]:
        """금반언 청구항 조회 — 현재 구현에서는 미지원 (빈 리스트 반환)."""
        return []

    def merge_results(
        self,
        rdb_results: list[dict],
        rag_results: list[dict],
        top_n: int = 10
    ) -> list[dict]:
        """RDB 검색 결과와 RAG 검색 결과 병합."""
        rdb_patents = {r['patent_id']: r for r in rdb_results}
        rag_patents = {r.get('patent_id', ''): r for r in rag_results}

        merged = []

        intersection = set(rdb_patents.keys()) & set(rag_patents.keys())
        for pid in intersection:
            result = rdb_patents[pid].copy()
            result['source'] = 'both'
            result['rag_score'] = rag_patents[pid].get('score', 0)
            merged.append(result)

        for pid in set(rag_patents.keys()) - intersection:
            result = rag_patents[pid].copy()
            merged.append(result)

        for pid in set(rdb_patents.keys()) - intersection:
            result = rdb_patents[pid].copy()
            merged.append(result)

        def sort_key(x):
            source_priority = {'both': 0, 'rag': 1, 'rdb': 2, 'fulltext': 2}
            return (
                source_priority.get(x.get('source', 'rdb'), 3),
                -x.get('match_count', 0),
                -x.get('rag_score', 0)
            )

        merged.sort(key=sort_key)
        return merged[:top_n]


def extract_keywords(text_input: str) -> list[str]:
    """사용자 입력에서 키워드 추출."""
    stopwords = {
        '있는', '하는', '하고', '했어', '만들', '개발', '출시', '예정',
        '제품', '기획', '중이야', '거야', '했어', '있어', '이야',
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would'
    }

    words = re.findall(r'[가-힣]{2,}|[A-Za-z]{3,}[-A-Za-z0-9]*', text_input)

    keywords = []
    seen = set()
    for word in words:
        lower_word = word.lower()
        if lower_word not in stopwords and lower_word not in seen:
            keywords.append(word)
            seen.add(lower_word)

    return keywords
