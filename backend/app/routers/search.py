"""
검색 API 라우터
- 하이브리드 검색 (RDB + RAG)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.services.search_service import SearchService, extract_keywords

router = APIRouter()


@router.get("/keywords")
async def search_by_keywords(
    q: str = Query(..., description="검색어"),
    limit: int = Query(20, ge=1, le=100),
    ipc: Optional[str] = Query(None, description="IPC 분류코드 필터"),
    db: Session = Depends(get_db)
):
    """
    키워드 기반 특허 청구항 검색

    - 사용자 입력에서 키워드 추출
    - claim_elements 테이블에서 매칭
    - 금반언 적용 (삭제된 청구항 제외)
    """
    # 키워드 추출
    keywords = extract_keywords(q)

    if not keywords:
        return {
            "query": q,
            "keywords": [],
            "results": [],
            "message": "검색 가능한 키워드가 없습니다."
        }

    # RDB 검색
    service = SearchService(db)
    results = service.search_by_keywords(
        keywords=keywords,
        limit=limit,
        ipc_filter=ipc
    )

    return {
        "query": q,
        "keywords": keywords,
        "total": len(results),
        "results": results
    }


@router.get("/fulltext")
async def search_fulltext(
    q: str = Query(..., description="검색어"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    전문 검색 (MySQL FULLTEXT)
    """
    service = SearchService(db)

    try:
        results = service.search_fulltext(q, limit)
    except Exception as e:
        # FULLTEXT 인덱스가 없을 경우 키워드 검색으로 폴백
        keywords = extract_keywords(q)
        results = service.search_by_keywords(keywords, limit)

    return {
        "query": q,
        "total": len(results),
        "results": results
    }


@router.get("/patent/{patent_id}/estoppel")
async def get_estoppel_claims(
    patent_id: int,
    db: Session = Depends(get_db)
):
    """
    특허의 금반언 청구항 조회

    - 출원 시에는 있었으나 등록 시 삭제된 청구항
    - 침해 판단에서 제외되어야 함
    """
    service = SearchService(db)
    estoppel_claims = service.get_estoppel_claims(patent_id)

    return {
        "patent_id": patent_id,
        "estoppel_claims": estoppel_claims,
        "count": len(estoppel_claims)
    }


@router.post("/hybrid")
async def hybrid_search(
    q: str = Query(..., description="검색어"),
    rag_results: list[dict] = [],  # ChromaDB에서 받은 결과
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    하이브리드 검색 (RDB + RAG 결과 병합)

    - RDB: 키워드 정확 매칭
    - RAG: 의미적 유사도 (ChromaDB)
    - 교집합 우선 정렬
    """
    # 키워드 추출 및 RDB 검색
    keywords = extract_keywords(q)
    service = SearchService(db)

    rdb_results = service.search_by_keywords(keywords, limit=20) if keywords else []

    # 결과 병합
    merged = service.merge_results(rdb_results, rag_results, top_n=limit)

    return {
        "query": q,
        "keywords": keywords,
        "rdb_count": len(rdb_results),
        "rag_count": len(rag_results),
        "merged_count": len(merged),
        "results": merged
    }
