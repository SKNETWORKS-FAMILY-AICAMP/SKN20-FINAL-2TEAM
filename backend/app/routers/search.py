"""
검색 API 라우터
- 키워드 검색 (claim_keywords 테이블)
- 전문 검색 (LIKE 폴백)
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
    db: Session = Depends(get_db)
):
    """키워드 기반 특허 청구항 검색"""
    keywords = extract_keywords(q)

    if not keywords:
        return {
            "query": q,
            "keywords": [],
            "results": [],
            "message": "검색 가능한 키워드가 없습니다."
        }

    service = SearchService(db)
    results = service.search_by_keywords(keywords=keywords, limit=limit)

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
    """전문 검색"""
    service = SearchService(db)

    try:
        results = service.search_fulltext(q, limit)
    except Exception:
        keywords = extract_keywords(q)
        results = service.search_by_keywords(keywords, limit)

    return {
        "query": q,
        "total": len(results),
        "results": results
    }


@router.post("/hybrid")
async def hybrid_search(
    q: str = Query(..., description="검색어"),
    rag_results: list[dict] = [],
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """하이브리드 검색 (RDB + RAG 결과 병합)"""
    keywords = extract_keywords(q)
    service = SearchService(db)

    rdb_results = service.search_by_keywords(keywords, limit=20) if keywords else []
    merged = service.merge_results(rdb_results, rag_results, top_n=limit)

    return {
        "query": q,
        "keywords": keywords,
        "rdb_count": len(rdb_results),
        "rag_count": len(rag_results),
        "merged_count": len(merged),
        "results": merged
    }
