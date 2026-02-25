"""스모크 테스트: RAG 파이프라인 연동 확인.

테스트 데이터셋 없이 쿼리 하나로 전체 파이프라인이 동작하는지 확인합니다.
정답 여부는 보지 않고, 각 단계가 에러 없이 완료되는지만 검증합니다.

사용법:
    cd C:\\SKN20-FINAL-2TEAM
    python -m rag.test.smoke_test
"""
import sys
import io
from pathlib import Path

# Windows cp949 인코딩 에러 방지
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

QUERY = "나이아신아마이드 5% 함유 미백 크림"

passed = 0
failed = 0


def check(name, fn):
    global passed, failed
    try:
        result = fn()
        passed += 1
        print(f"  [OK] {name}")
        return result
    except Exception as e:
        failed += 1
        print(f"  [FAIL] {name} - {type(e).__name__}: {e}")
        return None


print(f"\n{'='*50}")
print(f"RAG 스모크 테스트")
print(f"쿼리: {QUERY}")
print(f"{'='*50}")

# ── 1. config 로드 ──
print("\n[1] config")
config = check("config 임포트", lambda: __import__("rag.config", fromlist=["config"]))

# ── 2. 키워드 추출 ──
print("\n[2] 키워드 추출")
from rag.search.filter import extract_keywords
keywords = check("extract_keywords", lambda: extract_keywords(QUERY))
if keywords:
    print(f"       → {keywords}")

# ── 3. 사전필터링 ──
print("\n[3] 사전필터링")
from rag.search.filter import prefilter_by_keywords
prefilter = check("prefilter_by_keywords", lambda: prefilter_by_keywords(keywords or []))
if prefilter:
    _pids, _cids = prefilter
    print(f"       → {len(_cids)}개 청크, {len(_pids)}개 특허")

# ── 4. Dense 검색 (ChromaDB) ──
print("\n[4] Dense 검색 (ChromaDB)")
from rag.search.retriever import dense_search
allowed = prefilter[1] if prefilter else None
dense_results = check("dense_search", lambda: dense_search(QUERY, top_k=10, allowed_chunk_ids=allowed))
if dense_results:
    print(f"       → {len(dense_results)}건")

# ── 5. Sparse 검색 (BM25) ──
print("\n[5] Sparse 검색 (BM25)")
from rag.search.retriever import sparse_search
sparse_results = check("sparse_search", lambda: sparse_search(QUERY, top_k=10, allowed_chunk_ids=allowed))
if sparse_results:
    print(f"       → {len(sparse_results)}건")

# ── 6. RRF + Patent Collapse ──
print("\n[6] RRF + Patent Collapse")
from rag.search.retriever import reciprocal_rank_fusion, patent_collapse
dense_merged = [(cid, dist) for cid, dist, _ in (dense_results or [])]
dense_meta = {cid: meta for cid, _, meta in (dense_results or [])}
rrf = check("reciprocal_rank_fusion", lambda: reciprocal_rank_fusion(dense_merged, sparse_results or []))
if rrf:
    print(f"       → RRF {len(rrf)}건")
collapsed = check("patent_collapse", lambda: patent_collapse(rrf or [], dense_meta))
if collapsed:
    print(f"       → Collapse {len(collapsed)}건")

# ── 7. ParentDB 필터링 + 보강 ──
print("\n[7] ParentDB 필터링 + 보강")
from rag.search.filter import ParentDB, apply_rdb_filter
parent_db = check("ParentDB 로드", lambda: ParentDB())
filtered = check("apply_rdb_filter", lambda: apply_rdb_filter(collapsed or [], parent_db)) if parent_db else None
if filtered:
    print(f"       → {len(filtered)}건")

# ── 9. search() 통합 호출 ──
print("\n[9] search() 통합 호출")
from rag.search.pipeline import search
search_results = check("search()", lambda: search(QUERY))
if search_results:
    print(f"       → {len(search_results)}건")

# ── 10. generate_fto() (GPT-4o-mini) ──
print("\n[10] generate_fto() - GPT-4o-mini 호출")
from rag.generate import build_fto_prompt, call_llm, parse_fto_response
messages = check("build_fto_prompt", lambda: build_fto_prompt(search_results or [], QUERY))
raw = check("call_llm (GPT-4o-mini)", lambda: call_llm(messages)) if messages else None
if raw:
    print(f"       → 응답 {len(raw)}자")
parsed = check("parse_fto_response", lambda: parse_fto_response(raw)) if raw else None
if parsed:
    n = len(parsed.get("patent_analyses", []))
    print(f"       → {n}건 분석 파싱 완료")

# ── 11. analyze() 통합 호출 ──
print("\n[11] analyze() 통합 호출 (search + generate)")
from rag.search.pipeline import analyze
final = check("analyze()", lambda: analyze(QUERY))
if final:
    n_search = len(final.get("search_results", []))
    n_fto = len(final.get("fto_result", {}).get("patent_analyses", []))
    print(f"       → 검색 {n_search}건, FTO 분석 {n_fto}건")

# ── 결과 ──
print(f"\n{'='*50}")
total = passed + failed
print(f"결과: {passed}/{total} OK, {failed}/{total} FAIL")
if failed == 0:
    print("ALL PASSED - 파이프라인 정상 작동!")
else:
    print(f"{failed}개 단계에서 문제 발생")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
