"""BINI RAG - 특허 침해 검색 + 분석 시스템.

사용자가 출시하려는 제품을 설명하면, 침해 가능성이 있는 등록 특허를 검색하고
sLLM으로 침해 분석을 수행합니다.

파이프라인 흐름:
    사용자 입력
    → filter.py           (키워드 추출 + 사전필터링 → 문서 풀 축소)
    → retriever.py        (Dense+Sparse 검색 — KURE-v1 + BM25)
    → retriever.py        (RRF 점수 합산 + Patent Collapse)
    → filter.py           (등록 상태 필터 + 금반언 정보 첨부)
    → generate.py         (sLLM 침해 분석 — vLLM / GPT-4o-mini)
    → 최종 결과 반환

진입점:
    from rag.search.pipeline import search   # 검색만
    from rag.search.pipeline import analyze  # 검색 + 분석
    from rag.backend_adapter import analyze_product, search_only  # 백엔드용
"""
