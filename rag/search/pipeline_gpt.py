"""RAG 파이프라인 — GPT 전용 버전.

원본: pipeline.py
변경:
  1. dense_search → retriever_gpt (RunPod Serverless KURE-v1)
  2. generate_fto → generate_gpt (OpenAI GPT)
  나머지(sparse, RRF, collapse, filter)는 원본 그대로 사용.
"""
from .. import config
from .retriever_gpt import dense_search, sparse_search, reciprocal_rank_fusion, patent_collapse
from .filter import apply_rdb_filter, ParentDB, MySQLParentDB, prefilter_by_keywords, extract_keywords


# ══════════════════════════════════════════════════════
# 검색 파이프라인 (RunPod Dense + 로컬 Sparse)
# ══════════════════════════════════════════════════════

def search(
    query: str,
    top_k: int = None,
    dense_top_k: int = None,
    sparse_top_k: int = None,
    rrf_k: int = None,
    rrf_weights: tuple[float, float] = None,
    verbose: bool = False,
) -> list[dict]:
    """전체 RAG 검색 파이프라인 (RunPod 버전).

    dense_search()만 RunPod API를 호출하고, 나머지는 로컬에서 처리.
    """
    top_k = top_k or config.FINAL_TOP_K
    dense_top_k = dense_top_k or config.DENSE_TOP_K
    sparse_top_k = sparse_top_k or config.BM25_TOP_K

    # 1. 키워드 추출 + 사전필터링
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

    # 2. Dense 검색 (RunPod KURE-v1)
    if verbose:
        print("[Dense] RunPod Serverless KURE-v1 임베딩 요청 중...")
    d_results = dense_search(query, top_k=dense_top_k, allowed_chunk_ids=allowed_chunk_ids)
    dense_meta: dict[str, dict] = {}
    dense_merged = []
    for cid, dist, meta in d_results:
        dense_merged.append((cid, dist))
        dense_meta[cid] = meta

    # 3. Sparse 검색 (로컬 BM25)
    sparse_merged = sparse_search(query, top_k=sparse_top_k, allowed_chunk_ids=allowed_chunk_ids)

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

    # 5. Sparse-only 메타데이터 보충
    sparse_only_ids = [cid for cid, _ in rrf_results if cid not in dense_meta]
    if sparse_only_ids:
        col = _get_collection_for_meta()
        batch_size = 5000
        for i in range(0, len(sparse_only_ids), batch_size):
            batch_ids = sparse_only_ids[i:i + batch_size]
            got = col.get(ids=batch_ids, include=["metadatas"])
            for cid, meta in zip(got["ids"], got["metadatas"]):
                dense_meta[cid] = meta

    # 6. Patent Collapse
    collapsed = patent_collapse(rrf_results, dense_meta, top_k=top_k)

    if verbose:
        print(f"[Collapse] {len(collapsed)}개 특허")

    # 7. ParentDB 필터링 + 보강
    try:
        parent_db = ParentDB()
    except FileNotFoundError:
        try:
            parent_db = MySQLParentDB()
            if verbose:
                print("[ParentDB] SQLite 없음 → MySQL RDS 폴백 사용")
        except Exception as e:
            if verbose:
                print(f"[ParentDB] MySQL 폴백도 실패: {e} → 메타데이터 보강 없이 반환")
            return collapsed

    results = apply_rdb_filter(collapsed, parent_db)

    # 8. MIN_SCORE 필터
    if config.MIN_SCORE > 0:
        results = [r for r in results if r.get("score", 0) >= config.MIN_SCORE]

    if verbose:
        print(f"[필터] {len(results)}개 최종 결과")

    return results


def _get_collection_for_meta():
    """Sparse-only 메타데이터 보충용 ChromaDB 컬렉션."""
    from .retriever_gpt import _get_collection
    return _get_collection()


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

    GPT 버전: generate_gpt.generate_fto() 사용.
    """
    from ..generate_gpt import generate_fto

    search_results = search(query, top_k=top_k, verbose=verbose, **search_kwargs)

    if verbose:
        print(f"\n[FTO-GPT 분석 시작] 상위 {config.GENERATE_INPUT_N}건 → {config.GENERATE_OUTPUT_N}건 선별")

    fto_result = generate_fto(search_results, query, verbose=verbose)

    return {
        "query": query,
        "search_results": search_results,
        "fto_result": fto_result,
    }
