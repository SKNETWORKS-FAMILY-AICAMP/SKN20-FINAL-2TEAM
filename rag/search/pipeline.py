"""RAG 파이프라인 오케스트레이터. 이 파일이 검색의 진입점입니다.

하는 일:
    search() 함수 하나로 전체 파이프라인을 실행합니다:

    사용자 입력
    → [1] filter.py        : 키워드 추출 + 사전필터링 → 78K→~1K 문서 풀 축소
    → [2] retriever.py     : Dense+Sparse 검색 (축소된 풀 내)
    → [3] retriever.py     : RRF + Patent Collapse
    → [4] filter.py        : 등록 필터 + 금반언 + 데이터 보강
    → 최종 결과 반환

사용법:
    from rag.search.pipeline import search
    results = search("헤스페리딘이 포함된 한방 액제", verbose=True)

관계:
    - 같은 search/ 패키지 내 retriever.py, filter.py를 호출하는 중앙 모듈
    - evaluate.py, backend_adapter.py가 이 파일의 search()를 사용
"""
from .. import config
from .retriever import dense_search, sparse_search, reciprocal_rank_fusion, patent_collapse
from .filter import apply_rdb_filter, ClaimsDBInterface, SQLiteClaimsDB, ParentDB, prefilter_by_keywords, extract_keywords


# ══════════════════════════════════════════════════════
# 부모 DB 보강 (원문서 정보 첨부)
# ══════════════════════════════════════════════════════

def _enrich_with_parent_db(results: list[dict], verbose: bool = False) -> list[dict]:
    """검색 결과에 부모 DB(parent.db) 원문서 정보 첨부.

    검색은 경량 자식 청크로 수행하고, 결과 반환 시
    부모 DB에서 원문서 메타데이터·청크 구조를 보강합니다.
    """
    try:
        parent_db = ParentDB()
    except FileNotFoundError:
        if verbose:
            print("[부모DB] parent.db 없음 — 보강 건너뜀")
        return results

    enriched = 0
    for result in results:
        apply_num = result.get("patent_id", "")
        parent = parent_db.get_parent(apply_num)
        if not parent:
            continue
        enriched += 1

        meta = result.setdefault("metadata", {})

        # 1) 기존 메타데이터 보충 (빈 값만 채움)
        for key in ("invention_title", "abstract", "regit_num", "register_status"):
            if not meta.get(key) and parent.get(key):
                meta[key] = parent[key]
        if not meta.get("ipc") and parent.get("ipc"):
            meta["ipc"] = parent["ipc"]

        # 2) 부모 DB 전용 메타데이터 추가
        for key in ("invention_title_eng", "application_date", "open_date",
                     "register_date", "applicant"):
            if parent.get(key):
                meta[key] = parent[key]

        # 3) 청크 구조 정보
        result["chunk_ids"] = parent.get("chunk_ids", [])
        result["claim_groups"] = parent.get("claim_groups", {})

        # 4) 원문 청구항 텍스트 (G 모듈·프론트엔드 활용)
        result["claim_pub_text"] = parent.get("claim_pub", "")
        result["claim_regit_text"] = parent.get("claim_regit", "")

    if verbose:
        print(f"[부모DB] {enriched}/{len(results)}건 보강 완료")

    return results


# ══════════════════════════════════════════════════════
# 검색 파이프라인 (하이브리드 → RRF → 필터)
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

    사용자 입력 → 사전필터링 → 하이브리드 서치 → RRF → Patent Collapse → RDB 필터링

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

    # 1. 키워드 추출 + 사전필터링 (78K → ~1K 문서 풀 축소)
    allowed_chunk_ids = None
    extracted_keywords = extract_keywords(query)
    if verbose:
        print(f"[키워드 추출] {len(extracted_keywords)}개: {extracted_keywords}")

    prefilter_result = prefilter_by_keywords(extracted_keywords)
    if prefilter_result is not None:
        _patent_ids, allowed_chunk_ids = prefilter_result
        if verbose:
            print(f"[사전필터링] {len(allowed_chunk_ids)}개 청크, {len(_patent_ids)}개 특허로 축소")
    else:
        if verbose:
            print("[사전필터링] 매칭 없음 — 전체 문서 대상 검색")

    # 2. 하이브리드 서치 (Dense+Sparse 검색)
    # Dense 검색: KURE-v1 임베딩 → ChromaDB cosine distance (사전필터링 적용)
    d_results = dense_search(query, top_k=dense_top_k, allowed_chunk_ids=allowed_chunk_ids)
    dense_meta: dict[str, dict] = {}
    dense_merged = []
    for cid, dist, meta in d_results:
        dense_merged.append((cid, dist))
        dense_meta[cid] = meta

    # Sparse 검색: kiwipiepy 토크나이징 → BM25 스코어링 (사전필터링 적용)
    sparse_merged = sparse_search(query, top_k=sparse_top_k, allowed_chunk_ids=allowed_chunk_ids)

    if verbose:
        print(f"[Dense] {len(dense_merged)}개 후보")
        print(f"[Sparse] {len(sparse_merged)}개 후보")

    # 3. RRF
    rrf_results = reciprocal_rank_fusion(
        dense_merged, sparse_merged,
        k=rrf_k, weights=rrf_weights,
    )

    if verbose:
        print(f"[RRF] {len(rrf_results)}개 합산")

    # 4. Sparse-only 결과의 메타데이터 보충 (Dense에 없었던 chunk는 ChromaDB에서 보충)
    sparse_only_ids = [cid for cid, _ in rrf_results if cid not in dense_meta]
    if sparse_only_ids:
        from .retriever import _get_collection
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
        #         → from .filter import MySQLClaimsDB
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

    # 8. 부모 DB 보강 (원문서 정보 첨부)
    results = _enrich_with_parent_db(results, verbose=verbose)

    return results


# ══════════════════════════════════════════════════════
# RAG+G 통합 파이프라인 (search → generate)
# ══════════════════════════════════════════════════════

def analyze(
    query: str,
    top_k: int = None,
    verbose: bool = False,
    **search_kwargs,
) -> dict:
    """전체 RAG+G 파이프라인. search() -> generate_fto() -> 최종 응답.

    Args:
        query: 사용자 입력 (제품 설명).
        top_k: 검색 결과 수 (search()에 전달).
        verbose: 중간 로그 출력.
        **search_kwargs: search()에 전달할 추가 파라미터.

    Returns:
        {"query": str, "search_results": list, "fto_result": dict}
    """
    from ..generate import generate_fto

    search_results = search(query, top_k=top_k, verbose=verbose, **search_kwargs)

    if verbose:
        print(f"\n[FTO 분석 시작] 상위 {config.GENERATE_INPUT_N}건 → {config.GENERATE_OUTPUT_N}건 선별")

    fto_result = generate_fto(search_results, query, verbose=verbose)

    return {
        "query": query,
        "search_results": search_results,
        "fto_result": fto_result,
    }
