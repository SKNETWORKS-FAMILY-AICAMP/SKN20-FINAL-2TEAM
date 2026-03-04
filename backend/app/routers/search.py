"""
검색 API 라우터
- 키워드 검색 (claim_keywords 테이블)
- 전문 검색 (LIKE 폴백)
- KIPRIS Plus 특허 PDF 조회
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
import httpx
import os
import xml.etree.ElementTree as ET

from app.database import get_db
from app.config import settings
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


@router.get("/patent-pdf")
async def get_patent_pdf(
    apply_num: str = Query(..., description="출원번호 (예: 10-2005-0050026)"),
):
    """KIPRIS Plus API로 특허 원문 PDF URL을 조회하여 JSON 반환."""
    api_key = settings.KIPRIS_API_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="KIPRIS API 키가 설정되지 않았습니다.")

    # 하이픈 제거
    app_num = apply_num.replace("-", "")

    url = (
        f"http://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice/"
        f"getAnnFullTextInfoSearch?applicationNumber={app_num}&ServiceKey={api_key}"
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KIPRIS API 호출 실패: {e}")

    # XML 파싱 → <path> 추출
    try:
        root = ET.fromstring(resp.text)
        path_el = root.find(".//path")
        if path_el is not None and path_el.text:
            return {"pdf_url": path_el.text.strip()}
    except ET.ParseError:
        pass

    # PDF 없으면 404 (프론트에서 KIPRIS 폴백 처리)
    raise HTTPException(status_code=404, detail="PDF 없음")
