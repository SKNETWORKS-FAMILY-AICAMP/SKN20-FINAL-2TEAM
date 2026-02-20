"""RAG 파이프라인 오케스트레이터. 이 파일이 검색의 진입점입니다.

하는 일:
    search() 함수 하나로 전체 파이프라인을 실행합니다:

    사용자 입력
    → [1] filter.py        : 동의어 확장 (GPT-4o-mini) + 사전필터링 → 78K→~1K 문서 풀 축소
    → [2] multi_query.py   : 성분 추출 + 쿼리 조합 생성 (예: 8개)
    → [3] retriever.py     : 각 쿼리 × Dense+Sparse 검색 (축소된 풀 내)
    → [4] retriever.py     : RRF + Patent Collapse
    → [5] filter.py        : 등록 필터 + 금반언 + 데이터 보강
    → 최종 결과 반환

사용법:
    from rag.pipeline import search
    results = search("헤스페리딘이 포함된 한방 액제", verbose=True)

관계:
    - 위에 나열된 모든 모듈을 호출하는 중앙 모듈
    - evaluate.py, backend_adapter.py가 이 파일의 search()를 사용
"""
from . import config
from .search.multi_query import generate_queries
from .search.retriever import dense_search, sparse_search, reciprocal_rank_fusion, patent_collapse
from .search.filter import apply_rdb_filter, ClaimsDBInterface, SQLiteClaimsDB, expand_synonyms, prefilter_by_keywords, extract_keywords


# ══════════════════════════════════════════════════════
# 검색 파이프라인 (멀티쿼리 → 하이브리드 → RRF → 필터)
# ══════════════════════════════════════════════════════

def search(
    query: str,
    top_k: int = None,
    claims_db: ClaimsDBInterface = None,
    dense_top_k: int = None,
    sparse_top_k: int = None,
    rrf_k: int = None,
    rrf_weights: tuple[float, float] = None,
    verbose: bool = False,
) -> list[dict]:
    """전체 RAG 검색 파이프라인.

    사용자 입력 → 멀티쿼리 → 하이브리드 서치 → RRF → Patent Collapse → RDB 필터링

    Args:
        query: 사용자 입력.
        top_k: 최종 반환 특허 수.
        claims_db: RDB 필터용. None이면 SQLiteClaimsDB 사용.
        dense_top_k: Dense 검색 top-k (멀티쿼리당).
        sparse_top_k: Sparse 검색 top-k (멀티쿼리당).
        rrf_k: RRF K 파라미터.
        rrf_weights: (dense_weight, sparse_weight).
        verbose: 중간 로그 출력.

    Returns:
        최종 검색 결과 리스트.
    """
    top_k = top_k or config.FINAL_TOP_K
    dense_top_k = dense_top_k or config.DENSE_TOP_K
    sparse_top_k = sparse_top_k or config.BM25_TOP_K

    # 1. 키워드 추출 + 동의어 확장 + 사전필터링 (78K → ~1K 문서 풀 축소)
    allowed_chunk_ids = None
    extracted_keywords = extract_keywords(query)
    if verbose:
        print(f"[키워드 추출] {len(extracted_keywords)}개: {extracted_keywords}")

    synonym_groups = expand_synonyms(extracted_keywords)
    if verbose:
        if synonym_groups:
            total_syns = sum(len(v) for v in synonym_groups.values())
            print(f"[동의어] {len(synonym_groups)}개 키워드 → {total_syns}개 확장:")
            for kw, syns in synonym_groups.items():
                print(f"  {kw}: {syns}")
        else:
            print("[동의어] 확장 없음 — 정규화 키워드만으로 검색")

    prefilter_result = prefilter_by_keywords(extracted_keywords, synonym_groups)
    if prefilter_result is not None:
        _patent_ids, allowed_chunk_ids = prefilter_result
        if verbose:
            print(f"[사전필터링] {len(allowed_chunk_ids)}개 청크, {len(_patent_ids)}개 특허로 축소")
    else:
        if verbose:
            print("[사전필터링] 매칭 없음 — 전체 문서 대상 검색")

    # 2. 멀티쿼리 생성
    queries = generate_queries(query)
    if verbose:
        print(f"[멀티쿼리] {len(queries)}개 생성:")
        for i, q in enumerate(queries):
            print(f"  {i}: {q}")

    # 3. 하이브리드 서치 (각 멀티쿼리별로 Dense+Sparse 실행, 최적 점수 유지)
    dense_all: dict[str, float] = {}   # chunk_id → 최소 distance (낮을수록 유사)
    dense_meta: dict[str, dict] = {}   # chunk_id → metadata (ChromaDB에서 직접)
    sparse_all: dict[str, float] = {}  # chunk_id → 최대 score (높을수록 관련)

    for q in queries:
        # Dense 검색: KURE-v1 임베딩 → ChromaDB cosine distance (사전필터링 적용)
        d_results = dense_search(q, top_k=dense_top_k, allowed_chunk_ids=allowed_chunk_ids)
        for cid, dist, meta in d_results:
            # 같은 청크가 여러 쿼리에서 나오면 가장 가까운 거리 유지
            if cid not in dense_all or dist < dense_all[cid]:
                dense_all[cid] = dist
                dense_meta[cid] = meta

        # Sparse 검색: kiwipiepy 토크나이징 → BM25 스코어링 (사전필터링 적용)
        s_results = sparse_search(q, top_k=sparse_top_k, allowed_chunk_ids=allowed_chunk_ids)
        for cid, score in s_results:
            # 같은 청크가 여러 쿼리에서 나오면 가장 높은 점수 유지
            if cid not in sparse_all or score > sparse_all[cid]:
                sparse_all[cid] = score

    dense_merged = list(dense_all.items())
    sparse_merged = list(sparse_all.items())

    if verbose:
        print(f"[Dense] {len(dense_merged)}개 후보")
        print(f"[Sparse] {len(sparse_merged)}개 후보")

    # 4. RRF
    rrf_results = reciprocal_rank_fusion(
        dense_merged, sparse_merged,
        k=rrf_k, weights=rrf_weights,
    )

    if verbose:
        print(f"[RRF] {len(rrf_results)}개 합산")

    # 5. Sparse-only 결과의 메타데이터 보충 (Dense에 없었던 chunk는 ChromaDB에서 보충)
    sparse_only_ids = [cid for cid, _ in rrf_results if cid not in dense_meta]
    if sparse_only_ids:
        from .search.retriever import _get_collection
        col = _get_collection()
        batch_size = 5000
        for i in range(0, len(sparse_only_ids), batch_size):
            batch_ids = sparse_only_ids[i:i + batch_size]
            got = col.get(ids=batch_ids, include=["metadatas"])
            for cid, meta in zip(got["ids"], got["metadatas"]):
                dense_meta[cid] = meta

    # 5. Patent Collapse (ChromaDB 메타데이터 직접 사용)
    collapsed = patent_collapse(rrf_results, dense_meta, top_k=top_k)

    if verbose:
        print(f"[Collapse] {len(collapsed)}개 특허")

    # 6. RDB 필터링 (등록 상태 확인 + 금반언 표시 + 청구항 데이터 보강)
    if claims_db is None:
        # ※ 현재: SQLite (claims_db.sqlite, 78,587건 완전 데이터)
        # ※ 추후: MySQLClaimsDB로 교체 (RDB 구축 완료 시)
        #         → from .search.filter import MySQLClaimsDB
        #         → claims_db = MySQLClaimsDB()
        try:
            claims_db = SQLiteClaimsDB()
        except FileNotFoundError:
            return collapsed

    results = apply_rdb_filter(collapsed, claims_db)

    # 7. MIN_SCORE 필터 (노이즈 제거 — RRF 점수가 너무 낮은 결과 제외)
    if config.MIN_SCORE > 0:
        results = [r for r in results if r.get("score", 0) >= config.MIN_SCORE]

    if verbose:
        print(f"[필터] {len(results)}개 최종 결과")

    return results
