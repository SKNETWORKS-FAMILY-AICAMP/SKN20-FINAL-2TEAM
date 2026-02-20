"""사전필터링 단독 검증: 동의어 확장 + 사전필터링이 정답을 보존하는지 확인.

하는 일:
    테스트셋의 각 쿼리에 대해 사전필터링만 단독 실행하고,
    정답 특허가 필터링된 풀에 포함되는지 확인합니다.

    GPU/KURE-v1/ChromaDB/BM25 불필요 -CSV + OpenAI API 키만 있으면 실행 가능.
    풀 evaluate 전에 먼저 돌려서 사전필터링의 안전성을 확인하는 용도.

검증 항목:
    1. 동의어 확장이 작동하는지 (API 키 유효, 결과 생성)
    2. 사전필터링 풀 크기 (78K → 얼마로 축소?)
    3. 정답 특허가 풀에 포함되는지 (커버리지) ← 핵심

사용법:
    python -m rag.eval.test_prefilter
    python -m rag.eval.test_prefilter --max-chunks 500
    python -m rag.eval.test_prefilter --no-synonym   # 동의어 없이 원본 키워드만

관계:
    - filter.py의 expand_synonyms(), prefilter_by_keywords() 직접 호출
    - evaluate.py의 load_test_dataset() 재사용
    - pipeline.py, retriever.py는 import하지 않음 (모델 로딩 회피)
"""
import argparse
import time
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path

from .. import config
from ..search.filter import extract_keywords, expand_synonyms, prefilter_by_keywords
from ..search.multi_query import extract_components, MAX_PAIR_COMPONENTS
from .evaluate import load_test_dataset

REPORT_DIR = Path(__file__).parent / "reports"


def test_prefilter(
    test_data: list[dict] = None,
    max_chunks: int = None,
    use_synonym: bool = True,
    verbose: bool = True,
) -> dict:
    """사전필터링 단독 검증.

    Args:
        test_data: 테스트 데이터. None이면 기본 데이터셋 로드.
        max_chunks: 사전필터링 최대 청크 수 (None이면 config 값 사용).
        use_synonym: False면 동의어 확장 스킵 (원본 키워드만 테스트).
        verbose: 쿼리별 상세 출력.

    Returns:
        검증 결과 dict.
    """
    if test_data is None:
        test_data = load_test_dataset()

    if max_chunks is not None:
        original_max = config.PREFILTER_MAX_CHUNKS
        config.PREFILTER_MAX_CHUNKS = max_chunks
        print(f"  PREFILTER_MAX_CHUNKS: {original_max} → {max_chunks} (임시 변경)")

    total = len(test_data)
    results = []

    # 집계 변수
    covered = 0           # 정답이 풀에 포함된 수
    synonym_success = 0   # 동의어 확장 성공 수
    synonym_fail = 0      # 동의어 확장 실패 수
    pool_sizes = []       # 각 쿼리의 풀 크기
    patent_counts = []    # 각 쿼리의 특허 수

    # label별 집계
    label_covered = defaultdict(int)
    label_total = defaultdict(int)

    print(f"\n{'='*70}")
    print(f"  사전필터링 검증 시작 ({total}건)")
    print(f"  동의어 확장: {'ON' if use_synonym else 'OFF'}")
    print(f"  PREFILTER_MAX_CHUNKS: {config.PREFILTER_MAX_CHUNKS}")
    print(f"{'='*70}")

    for i, row in enumerate(test_data):
        query = str(row.get("user_query", "")).strip()
        answer_apply = str(row.get("apply_num", "")).strip().replace("-", "")
        answer_regit = str(row.get("regit_num", "")).strip()
        label = str(row.get("label", "")).strip()

        if not query:
            continue

        label_total[label] += 1
        t0 = time.perf_counter()

        # 1. 키워드 추출 + 동의어 확장
        extracted_keywords = extract_keywords(query)
        if use_synonym:
            synonym_groups = expand_synonyms(extracted_keywords)
        else:
            synonym_groups = {}

        if synonym_groups:
            synonym_success += 1
        else:
            synonym_fail += 1

        # 2. 성분 추출 + 멀티쿼리 확장 (리트리버에 실제 전달되는 쿼리 목록)
        #    extract_components() 1회 호출 후 멀티쿼리를 인라인 생성 (API 중복 호출 방지)
        extracted = extract_components(query)
        components = extracted.get("components", [])
        context = extracted.get("context", [])
        context_str = " ".join(context) if context else ""

        multi_queries = [query]
        if components:
            for comp in components:
                q = f"{comp} {context_str}".strip()
                multi_queries.append(q)
            pair_comps = components[:MAX_PAIR_COMPONENTS]
            if len(pair_comps) >= 2:
                for pair in combinations(pair_comps, 2):
                    multi_queries.append(" ".join(pair))
            if len(components) >= 2:
                multi_queries.append(" ".join(components))
            seen = set()
            multi_queries = [q for q in multi_queries if not (q in seen or seen.add(q))]

        # 3. 사전필터링
        prefilter_result = prefilter_by_keywords(extracted_keywords, synonym_groups)

        elapsed = time.perf_counter() - t0

        # 동의어에서 실제 CSV 매칭에 사용되는 키워드 목록
        flat_keywords = []
        for syns in synonym_groups.values():
            flat_keywords.extend(syns)

        # 4. 정답 포함 여부 확인
        if prefilter_result is not None:
            patent_ids, chunk_ids = prefilter_result
            pool_size = len(chunk_ids)
            patent_count = len(patent_ids)
            pool_sizes.append(pool_size)
            patent_counts.append(patent_count)

            # 정답 확인: apply_num이 patent_ids에 있는지
            answer_in_pool = answer_apply in patent_ids

            if answer_in_pool:
                covered += 1
                label_covered[label] += 1
        else:
            # 사전필터링 실패 (매칭 없음) → 전체 검색 fallback이므로 "포함"으로 간주
            pool_size = None
            patent_count = None
            answer_in_pool = True  # fallback = 전체 검색 = 정답 포함
            covered += 1
            label_covered[label] += 1

        entry = {
            "idx": i,
            "query": query,
            "label": label,
            "answer_apply": answer_apply,
            "answer_regit": answer_regit,
            "synonym_groups": synonym_groups,
            "synonym_count": sum(len(v) for v in synonym_groups.values()),
            "keyword_count": len(synonym_groups),
            "flat_keywords": flat_keywords,
            "extracted_components": extracted.get("components", []),
            "extracted_context": extracted.get("context", []),
            "extract_method": extracted.get("method", ""),
            "multi_queries": multi_queries,
            "pool_size": pool_size,
            "patent_count": patent_count,
            "answer_in_pool": answer_in_pool,
            "elapsed": elapsed,
        }
        results.append(entry)

        if verbose:
            status = "[O] 포함" if answer_in_pool else "[X] 누락"
            pool_str = f"{pool_size}청크/{patent_count}특허" if pool_size is not None else "전체(fallback)"
            print(f"\n  [{i+1}/{total}] [{label}] {status} ({elapsed:.2f}s)")
            print(f"  쿼리: {query[:80]}")
            print(f"  정답: {answer_apply}")
            print(f"  풀: {pool_str}")
            if synonym_groups:
                for kw, syns in synonym_groups.items():
                    print(f"  동의어: {kw} → {syns}")
            print(f"  정규화 키워드: {extracted_keywords}")
            print(f"  CSV 검색 키워드: {flat_keywords}")
            print(f"  성분 추출({extracted.get('method','')}): {extracted.get('components',[])} | 맥락: {extracted.get('context',[])}")
            print(f"  멀티쿼리({len(multi_queries)}개):")
            for qi, mq in enumerate(multi_queries):
                print(f"    {qi+1}. {mq}")

    # 결과 집계
    coverage_rate = covered / total if total > 0 else 0
    avg_pool = sum(pool_sizes) / len(pool_sizes) if pool_sizes else 0
    min_pool = min(pool_sizes) if pool_sizes else 0
    max_pool = max(pool_sizes) if pool_sizes else 0

    summary = {
        "total": total,
        "covered": covered,
        "missed": total - covered,
        "coverage_rate": coverage_rate,
        "synonym_success": synonym_success,
        "synonym_fail": synonym_fail,
        "pool_avg": avg_pool,
        "pool_min": min_pool,
        "pool_max": max_pool,
        "patent_avg": sum(patent_counts) / len(patent_counts) if patent_counts else 0,
        "label_coverage": {
            label: {
                "covered": label_covered[label],
                "total": label_total[label],
                "rate": label_covered[label] / label_total[label] if label_total[label] > 0 else 0,
            }
            for label in sorted(label_total.keys())
        },
        "details": results,
    }

    # 요약 출력
    _print_summary(summary)

    # 보고서 저장
    report_path = _save_report(summary)
    if report_path:
        print(f"\n  보고서 저장: {report_path}")

    # config 복원
    if max_chunks is not None:
        config.PREFILTER_MAX_CHUNKS = original_max

    return summary


def _print_summary(summary: dict):
    """검증 결과 요약 출력."""
    total = summary["total"]
    covered = summary["covered"]
    missed = summary["missed"]
    rate = summary["coverage_rate"]

    print(f"\n{'='*70}")
    print(f"  사전필터링 검증 결과")
    print(f"{'='*70}")

    print(f"\n  [커버리지]")
    print(f"  정답 포함: {covered}/{total} ({rate:.1%})")
    print(f"  정답 누락: {missed}/{total} ({1-rate:.1%})")

    print(f"\n  [동의어 확장]")
    print(f"  성공: {summary['synonym_success']}건")
    print(f"  실패/스킵: {summary['synonym_fail']}건")

    print(f"\n  [풀 크기]")
    print(f"  평균: {summary['pool_avg']:.0f}개 청크 / {summary['patent_avg']:.0f}개 특허")
    print(f"  최소: {summary['pool_min']}개 청크")
    print(f"  최대: {summary['pool_max']}개 청크")

    print(f"\n  [label별 커버리지]")
    for label, info in summary["label_coverage"].items():
        print(f"  {label}: {info['covered']}/{info['total']} ({info['rate']:.1%})")

    # 누락 목록
    miss_list = [d for d in summary["details"] if not d["answer_in_pool"]]
    if miss_list:
        print(f"\n  [누락 목록] ({len(miss_list)}건) -사전필터링이 정답을 제외함")
        print(f"  {'─'*65}")
        for d in miss_list:
            print(f"  [{d['label']}] 정답={d['answer_apply']}")
            print(f"    쿼리: {d['query'][:70]}")
            if d['synonym_groups']:
                keywords = ", ".join(d['synonym_groups'].keys())
                print(f"    추출 키워드: {keywords}")
            print(f"    풀: {d['pool_size']}청크/{d['patent_count']}특허")

    print(f"\n{'='*70}")


def _save_report(summary: dict) -> Path | None:
    """검증 결과를 텍스트 보고서로 저장."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"prefilter_{timestamp}.txt"

    lines = []
    lines.append("=" * 70)
    lines.append(f"사전필터링 검증 보고서  ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    lines.append("=" * 70)
    lines.append("")

    # 설정
    lines.append("[설정]")
    lines.append(f"  PREFILTER_MAX_CHUNKS: {config.PREFILTER_MAX_CHUNKS}")
    lines.append(f"  OPENAI_API_KEY: {'설정됨' if config.OPENAI_API_KEY else '미설정'}")
    lines.append("")

    # 요약
    total = summary["total"]
    lines.append("[커버리지]")
    lines.append(f"  정답 포함: {summary['covered']}/{total} ({summary['coverage_rate']:.1%})")
    lines.append(f"  정답 누락: {summary['missed']}/{total}")
    lines.append("")

    lines.append("[동의어 확장]")
    lines.append(f"  성공: {summary['synonym_success']}건")
    lines.append(f"  실패/스킵: {summary['synonym_fail']}건")
    lines.append("")

    lines.append("[풀 크기]")
    lines.append(f"  평균: {summary['pool_avg']:.0f}개 청크 / {summary['patent_avg']:.0f}개 특허")
    lines.append(f"  최소: {summary['pool_min']}개 청크")
    lines.append(f"  최대: {summary['pool_max']}개 청크")
    lines.append("")

    lines.append("[label별 커버리지]")
    for label, info in summary["label_coverage"].items():
        lines.append(f"  {label}: {info['covered']}/{info['total']} ({info['rate']:.1%})")
    lines.append("")

    # 누락 목록
    miss_list = [d for d in summary["details"] if not d["answer_in_pool"]]
    if miss_list:
        lines.append(f"[누락 목록] ({len(miss_list)}건)")
        for d in miss_list:
            lines.append(f"  [{d['label']}] 정답={d['answer_apply']}")
            lines.append(f"    쿼리: {d['query'][:100]}")
            if d["synonym_groups"]:
                for kw, syns in d["synonym_groups"].items():
                    lines.append(f"    동의어: {kw} → {syns}")
            lines.append(f"    CSV 검색 키워드: {d.get('flat_keywords', [])}")
            multi_queries = d.get("multi_queries", [])
            if multi_queries:
                lines.append(f"    멀티쿼리({len(multi_queries)}개):")
                for qi, mq in enumerate(multi_queries):
                    lines.append(f"      {qi+1}. {mq}")
            lines.append(f"    풀: {d['pool_size']}청크/{d['patent_count']}특허")
        lines.append("")

    # 상세 결과
    lines.append("[상세 결과]")
    for d in summary["details"]:
        idx = d["idx"] + 1
        status = "포함" if d["answer_in_pool"] else "누락"
        pool_str = f"{d['pool_size']}청크/{d['patent_count']}특허" if d["pool_size"] is not None else "전체(fallback)"
        lines.append("")
        lines.append(f"--- [{idx}/{total}] [{d['label']}] {status} ({d['elapsed']:.2f}s) ---")
        lines.append(f"  쿼리: {d['query']}")
        lines.append(f"  정답: {d['answer_apply']}")
        lines.append(f"  풀: {pool_str}")
        if d["synonym_groups"]:
            for kw, syns in d["synonym_groups"].items():
                lines.append(f"  동의어: {kw} → {syns}")
        else:
            lines.append("  동의어: 확장 없음")
        lines.append(f"  CSV 검색 키워드: {d.get('flat_keywords', [])}")
        lines.append(f"  성분 추출({d.get('extract_method','')}):")
        lines.append(f"    성분: {d.get('extracted_components', [])}")
        lines.append(f"    맥락: {d.get('extracted_context', [])}")
        multi_queries = d.get("multi_queries", [])
        lines.append(f"  멀티쿼리({len(multi_queries)}개):")
        for qi, mq in enumerate(multi_queries):
            lines.append(f"    {qi+1}. {mq}")

    lines.append("")
    lines.append("=" * 70)

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ══════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="사전필터링 단독 검증")
    parser.add_argument("--max-chunks", type=int, default=None,
                        help="사전필터링 최대 청크 수 (기본: config 값)")
    parser.add_argument("--no-synonym", action="store_true",
                        help="동의어 확장 없이 테스트")
    parser.add_argument("--quiet", action="store_true",
                        help="쿼리별 상세 출력 생략")
    args = parser.parse_args()

    test_prefilter(
        max_chunks=args.max_chunks,
        use_synonym=not args.no_synonym,
        verbose=not args.quiet,
    )
