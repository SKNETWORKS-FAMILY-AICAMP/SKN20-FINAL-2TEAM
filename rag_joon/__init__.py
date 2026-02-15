"""BINI RAG - 특허 침해 검색 시스템.

사용자가 출시하려는 제품을 설명하면, 침해 가능성이 있는 등록 특허를 검색합니다.

파이프라인 흐름:
    사용자 입력
    → multi_query.py      (성분 추출 + 쿼리 조합 확장)
    → dense_search.py     (KURE-v1 임베딩 → ChromaDB 의미 검색)
    → sparse_search.py    (kiwipiepy 토크나이징 → BM25 키워드 검색)
    → rrf.py              (Dense+Sparse 점수 합산 → 같은 특허 청크 병합)
    → rdb_filter.py       (등록 상태 필터 + 금반언 정보 첨부)
    → 최종 결과 반환

진입점:
    from rag.pipeline import search
    results = search("헤스페리딘이 포함된 한방 액제")
"""
