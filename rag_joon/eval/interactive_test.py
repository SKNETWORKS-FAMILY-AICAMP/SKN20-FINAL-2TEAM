"""대화형 검색 테스트 REPL. 인덱스 빌드 후 검색을 직접 시험해볼 수 있습니다.

기능:
    - 대화형 모드: 쿼리 입력 → 성분 추출 결과 + 검색 결과 Top-K 표시
    - 평가 모드(--eval): 테스트셋으로 Hit Rate, MRR 자동 측정
    - 종료 시 세션 결과 자동 저장 (JSON + MD 보고서)

Usage:
    # rag 폴더의 상위 디렉토리에서 실행
    python -m rag.eval.interactive_test
    python -m rag.eval.interactive_test --verbose
    python -m rag.eval.interactive_test --eval
"""
import argparse
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .. import config
from ..pipeline import search
from ..search.multi_query import extract_components
from .evaluate import evaluate, load_test_dataset

KST = timezone(timedelta(hours=9))
REPORT_DIR = Path(__file__).parent / "reports" / "manual"

# ── 세션 기록 ────────────────────────────────────────

session_log = []


def _record_query(query: str, extracted: dict, results: list[dict], elapsed: float):
    """쿼리 실행 결과를 세션 로그에 추가."""
    # 검색 결과를 직렬화 가능한 형태로 변환 (JSON 저장용)
    serialized = []
    for i, r in enumerate(results, 1):
        meta = r.get("metadata", {})
        claims = r.get("claims", {})
        last_claims = claims.get("last_claims", [])
        indep_claims = [c for c in last_claims if c.get("claim_type") == "independent"]

        entry = {
            "rank": i,
            "patent_id": r.get("patent_id", ""),
            "regit_num": meta.get("regit_num", ""),
            "invention_title": meta.get("invention_title", ""),
            "score": round(r.get("score", 0), 6),
            "matched_claim_num": r.get("matched_claim_num", 0),
            "register_status": meta.get("register_status", ""),
            "ipc": meta.get("ipc", []),
            "abstract": meta.get("abstract", "")[:300],
            "claims_count": len(last_claims),
            "independent_claims_count": len(indep_claims),
            "independent_claims_text": [
                c.get("text", "")[:500] for c in indep_claims[:3]
            ],
            "estoppel_claim_numbers": r.get("estoppel_claim_numbers", []),
        }
        serialized.append(entry)

    session_log.append({
        "query_num": len(session_log) + 1,
        "timestamp": datetime.now(KST).strftime("%H:%M:%S"),
        "query": query,
        "components": extracted.get("components", []),
        "context": extracted.get("context", []),
        "elapsed_sec": round(elapsed, 3),
        "result_count": len(serialized),
        "results": serialized,
    })


def _save_session():
    """세션 로그를 JSON + MD로 저장."""
    if not session_log:
        print("  저장할 테스트 기록이 없습니다.")
        return

    now = datetime.now(KST)
    file_stem = now.strftime("%Y%m%d_%H%M")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # JSON 저장
    session_data = {
        "date": now.strftime("%Y-%m-%d"),
        "session_start": session_log[0]["timestamp"],
        "session_end": now.strftime("%H:%M:%S"),
        "config": {
            "embed_model": config.EMBED_MODEL,
            "dense_top_k": config.DENSE_TOP_K,
            "bm25_top_k": config.BM25_TOP_K,
            "rrf_weights": list(config.RRF_WEIGHTS),
            "rrf_k": config.RRF_K,
            "final_top_k": config.FINAL_TOP_K,
            "multi_query_mode": config.MULTI_QUERY_MODE,
            "estoppel_enabled": config.ESTOPPEL_ENABLED,
            "registered_only": config.REGISTERED_ONLY,
        },
        "total_queries": len(session_log),
        "avg_elapsed_sec": round(
            sum(q["elapsed_sec"] for q in session_log) / len(session_log), 3
        ),
        "queries": session_log,
    }

    json_path = REPORT_DIR / f"{file_stem}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)

    # MD 저장
    md_path = REPORT_DIR / f"{file_stem}.md"
    md_lines = _build_md_report(session_data)
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"\n  보고서 저장 완료:")
    print(f"    JSON: {json_path}")
    print(f"    MD:   {md_path}")


def _build_md_report(data: dict) -> list[str]:
    """세션 데이터를 마크다운 보고서로 변환."""
    lines = []
    lines.append("# RAG 수동 테스트 보고서")
    lines.append("")
    lines.append(f"> 날짜: {data['date']} | 세션: {data['session_start']} ~ {data['session_end']}")
    lines.append("")

    # 설정
    lines.append("## 설정")
    lines.append("")
    lines.append("| 항목 | 값 |")
    lines.append("|------|-----|")
    for k, v in data["config"].items():
        lines.append(f"| {k} | {v} |")
    lines.append(f"| 총 쿼리 수 | {data['total_queries']} |")
    lines.append(f"| 평균 응답시간 | {data['avg_elapsed_sec']}s |")
    lines.append("")

    # 쿼리별 결과
    lines.append("## 쿼리별 결과")
    lines.append("")

    for q in data["queries"]:
        lines.append(f"### #{q['query_num']} ({q['timestamp']})")
        lines.append("")
        lines.append(f"- **쿼리**: {q['query']}")
        lines.append(f"- **성분 추출**: {q['components']}")
        lines.append(f"- **맥락**: {q['context']}")
        lines.append(f"- **응답시간**: {q['elapsed_sec']}s | **결과 수**: {q['result_count']}건")
        lines.append("")

        if q["results"]:
            lines.append("| 순위 | 등록번호 | 점수 | 매칭항 | 발명 명칭 |")
            lines.append("|------|----------|------|--------|----------|")
            for r in q["results"]:
                title_short = r["invention_title"][:40]
                if len(r["invention_title"]) > 40:
                    title_short += "..."
                est = f" [금반언:{r['estoppel_claim_numbers']}]" if r["estoppel_claim_numbers"] else ""
                lines.append(
                    f"| {r['rank']} | `{r['regit_num']}` | {r['score']} "
                    f"| 제{r['matched_claim_num']}항 | {title_short}{est} |"
                )
            lines.append("")

            # 1위 상세
            top1 = q["results"][0]
            lines.append("**1위 상세:**")
            lines.append("")
            if top1.get("abstract"):
                lines.append(f"- 초록: {top1['abstract'][:200]}...")
            if top1.get("independent_claims_text"):
                lines.append(f"- 독립항 ({top1['independent_claims_count']}개):")
                for ci, ct in enumerate(top1["independent_claims_text"], 1):
                    lines.append(f"  - [{ci}] {ct[:200]}...")
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.append("*이 보고서는 수동 테스트 세션에서 자동 생성되었습니다.*")
    return lines


# ── REPL ─────────────────────────────────────────────

def run_repl(verbose: bool = False):
    """대화형 검색 REPL."""
    print("=" * 60)
    print("BINI RAG 대화형 검색 테스트")
    print("-" * 60)
    print("  명령어:")
    print("    /report       현재까지 결과를 보고서로 저장")
    print("    /claim N      마지막 결과의 N번째 특허 청구항 전문 보기")
    print("    /abstract N   마지막 결과의 N번째 특허 초록 전문 보기")
    print("    eval          테스트셋 평가 실행")
    print("    q, quit       종료 (자동 저장)")
    print(f"  종료 시 자동 저장: {REPORT_DIR}")
    print("=" * 60)

    last_results = []

    while True:
        try:
            query = input("\n검색> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            _save_session()
            print("종료.")
            break

        if not query:
            continue
        if query.lower() in ("q", "quit", "exit"):
            _save_session()
            print("종료.")
            break
        if query.lower() == "eval":
            run_eval(verbose=True)
            continue

        # 명령어 처리
        if query.startswith("/"):
            cmd_parts = query.split(maxsplit=1)
            cmd = cmd_parts[0].lower()
            cmd_arg = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

            if cmd == "/report":
                _save_session()

            elif cmd == "/claim":
                if not last_results:
                    print("  먼저 검색을 실행하세요.")
                elif cmd_arg.isdigit():
                    idx = int(cmd_arg) - 1
                    if 0 <= idx < len(last_results):
                        r = last_results[idx]
                        meta = r.get("metadata", {})
                        claims = r.get("claims", {})
                        last_claims = claims.get("last_claims", [])
                        print(f"\n  [{idx + 1}] {meta.get('invention_title', '?')} ({meta.get('regit_num', '?')})")
                        print(f"  등록 청구항 {len(last_claims)}개:")
                        print(f"  {'-' * 60}")
                        for cl in last_claims:
                            ctype = cl.get("claim_type", "")
                            text = cl.get("text", "")
                            label = "[독립항]" if ctype == "independent" else "[종속항]"
                            cnum = cl.get("claim_number", "?")
                            print(f"  제{cnum}항 {label}")
                            print(f"  {text}")
                            print()
                    else:
                        print(f"  범위 초과 (1~{len(last_results)})")
                else:
                    print("  사용법: /claim 번호 (예: /claim 1)")

            elif cmd == "/abstract":
                if not last_results:
                    print("  먼저 검색을 실행하세요.")
                elif cmd_arg.isdigit():
                    idx = int(cmd_arg) - 1
                    if 0 <= idx < len(last_results):
                        r = last_results[idx]
                        meta = r.get("metadata", {})
                        print(f"\n  [{idx + 1}] {meta.get('invention_title', '?')} ({meta.get('regit_num', '?')})")
                        print(f"  초록:")
                        print(f"  {'-' * 60}")
                        print(f"  {meta.get('abstract', '없음')}")
                    else:
                        print(f"  범위 초과 (1~{len(last_results)})")
                else:
                    print("  사용법: /abstract 번호 (예: /abstract 1)")

            else:
                print(f"  알 수 없는 명령어: {cmd}")
            continue

        # multi_query.py로 쿼리에서 성분·맥락 추출 → 표시
        extracted = extract_components(query)
        print(f"  성분: {extracted['components']}")
        print(f"  맥락: {extracted['context']}")

        # pipeline.search() 호출 → Dense+Sparse+RRF+필터링 전체 파이프라인 실행
        start = time.time()
        results = search(query, verbose=verbose)
        elapsed = time.time() - start
        print(f"  검색 시간: {elapsed:.3f}s")

        last_results = results

        if not results:
            print("  결과 없음.")
            _record_query(query, extracted, [], elapsed)
            continue

        print(f"\n  {'순위':<4} {'출원번호':<20} {'등록번호':<22} {'점수':<10} {'매칭항':<6} {'제목'}")
        print(f"  {'-'*90}")
        for i, r in enumerate(results):
            meta = r.get("metadata", {})
            title = meta.get("invention_title", "")[:40]
            pid = r.get("patent_id", "?")
            regit = meta.get("regit_num", "?")
            score = r.get("score", 0)
            claim = r.get("matched_claim_num", "?")
            estoppel = r.get("estoppel_claim_numbers", [])
            est_mark = f" [금반언:{estoppel}]" if estoppel else ""
            print(f"  {i+1:<4} {pid:<20} {regit:<22} {score:<10.6f} {claim:<6} {title}{est_mark}")

        # 세션 로그에 기록
        _record_query(query, extracted, results, elapsed)


def run_eval(verbose: bool = True):
    """테스트셋 기반 자동 평가. Hit Rate, MRR 등 정량 지표 측정."""
    print("\n테스트셋 평가 시작...")
    try:
        result = evaluate(verbose=verbose)
        return result
    except FileNotFoundError:
        print("테스트셋 파일을 찾을 수 없습니다.")
        return None


def main():
    """CLI 진입점. --eval 플래그로 평가 모드, 기본은 대화형 REPL."""
    parser = argparse.ArgumentParser(description="RAG 대화형 테스트")
    parser.add_argument("--verbose", "-v", action="store_true", help="상세 로그")
    parser.add_argument("--eval", action="store_true", help="테스트셋 평가만 실행")
    args = parser.parse_args()

    if args.eval:
        run_eval(verbose=True)
    else:
        run_repl(verbose=args.verbose)


if __name__ == "__main__":
    main()
