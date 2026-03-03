"""대화형 RAG 테스트 - 터미널에서 직접 검색 + FTO 분석 체험.

각 단계별 진행 상황을 실시간으로 표시합니다.

사용법:
    cd C:\\SKN20-FINAL-2TEAM
    python -m rag.test.interactive              # 검색 + FTO 분석
    python -m rag.test.interactive --search     # 검색만 (GPT 호출 없음)
"""
import sys
import io
import argparse

# Windows cp949 인코딩 에러 방지
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from rag import config
from rag.search.filter import (
    extract_keywords, prefilter_by_keywords,
    ParentDB, apply_rdb_filter,
)
from rag.search.retriever import (
    dense_search, sparse_search,
    reciprocal_rank_fusion, patent_collapse,
    _get_collection,
)
from rag.generate import generate, build_prompt, call_llm, parse_response


def step(num, total, msg):
    """단계 시작 표시 (즉시 출력)."""
    print(f"  [{num}/{total}] {msg}...", end="", flush=True)


def done(detail=""):
    """단계 완료 표시."""
    if detail:
        print(f" -> {detail}", flush=True)
    else:
        print(f" -> 완료", flush=True)


def run_search(query):
    """검색 파이프라인을 단계별로 실행."""
    total = 8

    # 1. 키워드 추출
    step(1, total, "키워드 추출 중")
    keywords = extract_keywords(query)
    done(f"{len(keywords)}개 {keywords}")

    # 2. 사전필터링
    step(2, total, "사전필터링 중")
    prefilter_result = prefilter_by_keywords(keywords)
    allowed_chunk_ids = None
    if prefilter_result is not None:
        _patent_ids, allowed_chunk_ids = prefilter_result
        done(f"{len(allowed_chunk_ids)}개 청크, {len(_patent_ids)}개 특허")
    else:
        done("매칭 없음 - 전체 대상 검색")

    # 3. Dense 검색
    step(3, total, "Dense 검색 중 (ChromaDB)")
    d_results = dense_search(query, top_k=config.DENSE_TOP_K, allowed_chunk_ids=allowed_chunk_ids)
    dense_meta = {}
    dense_merged = []
    for cid, dist, meta in d_results:
        dense_merged.append((cid, dist))
        dense_meta[cid] = meta
    done(f"{len(dense_merged)}건")

    # 4. Sparse 검색
    step(4, total, "Sparse 검색 중 (BM25)")
    sparse_merged = sparse_search(query, top_k=config.BM25_TOP_K, allowed_chunk_ids=allowed_chunk_ids)
    done(f"{len(sparse_merged)}건")

    # 5. RRF + Patent Collapse
    step(5, total, "RRF 합산 중")
    rrf_results = reciprocal_rank_fusion(
        dense_merged, sparse_merged,
        k=config.RRF_K, weights=config.RRF_WEIGHTS,
    )
    done(f"{len(rrf_results)}건")

    # Sparse-only 메타 보충
    sparse_only_ids = [cid for cid, _ in rrf_results if cid not in dense_meta]
    if sparse_only_ids:
        col = _get_collection()
        for i in range(0, len(sparse_only_ids), 5000):
            batch = sparse_only_ids[i:i + 5000]
            got = col.get(ids=batch, include=["metadatas"])
            for cid, meta in zip(got["ids"], got["metadatas"]):
                dense_meta[cid] = meta

    step(6, total, "Patent Collapse 중")
    collapsed = patent_collapse(rrf_results, dense_meta, top_k=config.FINAL_TOP_K)
    done(f"{len(collapsed)}건")

    # 6. ParentDB 필터링 + 보강
    step(7, total, "ParentDB 필터링 + 보강 중")
    try:
        parent_db = ParentDB()
    except FileNotFoundError:
        done("ParentDB 없음 - 건너뜀")
        return collapsed

    results = apply_rdb_filter(collapsed, parent_db)
    if config.MIN_SCORE > 0:
        results = [r for r in results if r.get("score", 0) >= config.MIN_SCORE]
    done(f"{len(results)}건")

    return results


def run_fto(search_results, query):
    """FTO 분석을 단계별로 실행 (1건씩 sLLM 호출)."""
    top_n = config.GENERATE_TOP_N
    total_steps = top_n
    analyses = []

    for i, result in enumerate(search_results[:top_n]):
        patent_id = result.get("patent_id", "unknown")
        meta = result.get("metadata", {})
        title = meta.get("invention_title", "")[:40]

        # 프롬프트 조립 + sLLM 호출
        step(i + 1, total_steps, f"sLLM 분석 중: {patent_id} ({title})")
        messages = build_prompt(result, query)

        try:
            raw = call_llm(messages)
            parsed = parse_response(raw)
            parsed["patent_id"] = patent_id
            parsed["score"] = result.get("score", 0)
            parsed["metadata"] = meta
            parsed["estoppel_claim_numbers"] = result.get("estoppel_claim_numbers", [])
            analyses.append(parsed)
            done(f"{parsed.get('label', '?')}")
        except Exception as e:
            done(f"실패: {e}")
            analyses.append({"patent_id": patent_id, "error": str(e)})

    return {"patent_analyses": analyses, "fto_opinion": "", "raw_output": ""}


def print_search_results(results):
    """검색 결과를 보기 좋게 출력."""
    if not results:
        print("\n  검색 결과 없음")
        return

    print(f"\n  {'='*60}")
    print(f"  검색 결과: {len(results)}건")
    print(f"  {'='*60}")

    for i, r in enumerate(results, 1):
        meta = r.get("metadata", {})
        title = meta.get("invention_title", "(제목 없음)")
        regit = meta.get("regit_num", "")
        status = meta.get("register_status", "")
        score = r.get("score", 0)
        abstract = meta.get("abstract", "")
        claim_num = r.get("matched_claim_num", "")
        estoppel = r.get("estoppel_claim_numbers", [])

        print(f"\n  [{i}] {title}")
        print(f"      등록번호: {regit}  |  상태: {status}  |  점수: {score:.4f}")
        print(f"      매칭 청구항: {claim_num}번  |  금반언: {estoppel if estoppel else '없음'}")
        if abstract:
            print(f"      초록: {abstract[:100]}{'...' if len(abstract) > 100 else ''}")


def print_fto_result(fto_result):
    """FTO 분석 결과를 보기 좋게 출력."""
    if not fto_result:
        print("\n  FTO 분석 결과 없음")
        return

    analyses = fto_result.get("patent_analyses", [])
    fto_opinion = fto_result.get("fto_opinion", "")

    print(f"\n  {'='*60}")
    print(f"  FTO 분석 결과: {len(analyses)}건")
    print(f"  {'='*60}")

    for a in analyses:
        pid = a.get("patent_id", "?")
        label = a.get("label", "?")
        logic = a.get("logic_consistency", "?")

        print(f"\n  --- 특허: {pid} ---")
        print(f"  판정: {label}  |  법리일관성: {logic}")

        comparisons = a.get("comparisons", [])
        if comparisons:
            print(f"  {'':2s}{'특허 구성요소':30s} | {'제품 구성요소':25s} | 대응")
            print(f"  {'-'*30} | {'-'*25} | {'-'*6}")
            for c in comparisons:
                pe = c.get("patent_element", "")[:30]
                ue = c.get("user_element", "")[:25]
                co = c.get("correspondence", "")
                print(f"  {pe:30s} | {ue:25s} | {co}")

    if fto_opinion:
        print(f"\n  {'='*60}")
        print(f"  종합 FTO 의견")
        print(f"  {'='*60}")
        print(f"  {fto_opinion}")


def main():
    parser = argparse.ArgumentParser(description="대화형 RAG 테스트")
    parser.add_argument("--search", action="store_true",
                        help="검색만 수행 (GPT 호출 없음)")
    args = parser.parse_args()

    mode = "검색" if args.search else "검색 + FTO 분석"

    print(f"\n{'='*60}")
    print(f"  RAG 대화형 테스트 ({mode})")
    print(f"  q 또는 quit 입력시 종료")
    print(f"{'='*60}")

    while True:
        try:
            query = input("\n  제품 설명 > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n  종료")
            break

        if not query:
            continue
        if query.lower() in ("q", "quit", "exit"):
            print("  종료")
            break

        print()
        print(f"  --- 검색 ---")

        try:
            search_results = run_search(query)
            print_search_results(search_results)

            if not args.search:
                print()
                print(f"  --- FTO 분석 ---")
                fto_result = run_fto(search_results, query)
                print_fto_result(fto_result)

        except Exception as e:
            print(f"\n  [ERROR] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
