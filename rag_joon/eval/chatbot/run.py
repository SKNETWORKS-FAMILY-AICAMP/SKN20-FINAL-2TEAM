"""GPT 기반 특허 침해 분석 챗봇 (테스트용).

목적:
    1. 리트리버가 제대로 된 값을 가져오는지 확인
    2. 검색→생성 전체 파이프라인이 채팅 기능으로 구현 가능한지 검증

흐름:
    사용자 제품 설명 입력
    → pipeline.search()로 관련 특허 검색
    → 검색 결과를 프롬프트에 삽입
    → OpenAI API 호출 → 침해 분석 생성
    → 후속 질문 가능 (대화 이력 유지)
    → 종료 시 대화 기록 자동 저장 (JSON + MD)

사용법:
    # rag 폴더의 상위 디렉토리에서 실행
    python -m rag.eval.chatbot.run
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from ... import config  # config.py가 .env를 자동 로드하므로 OPENAI_API_KEY 사용 가능
from ...pipeline import search

KST = timezone(timedelta(hours=9))
REPORT_DIR = Path(__file__).parent.parent / "reports" / "chatbot"

# ── 프롬프트 ──────────────────────────────────────────

SYSTEM_PROMPT = (
    "너는 특허 청구항과 사용자 제품 구성을 비교하여 "
    "구성요소별 대응 여부를 판단하고, "
    "그 결과에 따라 특허 침해 리스크를 평가하는 전문가이다.\n\n"
    "분석 시 다음 형식을 따라라:\n\n"
    "◆ 관련 특허 ◆\n"
    "검색된 특허의 등록번호와 제목\n\n"
    "◆ 구성 대비 ◆\n"
    "| 특허 구성요소 | 사용자 제품 | 대응 여부 |\n"
    "|---------------|-------------|----------|\n"
    "| ... | ... | 대응/미대응 |\n\n"
    "◆ 판단 ◆\n"
    "침해 여부에 대한 상세 분석\n\n"
    "◆ 결론 ◆\n"
    "최종 판단 (침해 가능성 높음/중간/낮음)\n\n"
    "규칙:\n"
    "- 금반언 청구항(estoppel)에 해당하는 청구항은 침해 판단 근거에서 제외할 것\n"
    "- 등록 청구항(last version)을 기준으로 판단할 것\n"
    "- 근거가 불충분하면 '판단불가'로 표시할 것"
)

MAX_CLAIM_LEN = 800
MAX_PATENTS = 3


# ── 검색 결과 포맷 ───────────────────────────────────

def _format_search_results(results: list[dict]) -> str:
    """검색 결과를 LLM 프롬프트용 텍스트로 포맷."""
    if not results:
        return "검색 결과가 없습니다."

    # 상위 N개 특허를 LLM이 이해할 수 있는 구조화된 텍스트로 변환
    parts = []
    for i, r in enumerate(results[:MAX_PATENTS]):
        meta = r.get("metadata", {})
        claims = r.get("claims", {})
        estoppel = r.get("estoppel_claim_numbers", [])

        part = f"--- 특허 {i + 1} ---\n"
        part += f"등록번호: {meta.get('regit_num', '?')}\n"
        part += f"제목: {meta.get('invention_title', '?')}\n"
        part += f"매칭 청구항: 제{r.get('matched_claim_num', '?')}항\n"
        part += f"관련도 점수: {r.get('score', 0):.4f}\n"

        if estoppel:
            part += f"금반언 청구항: {estoppel} (이 청구항들은 침해 판단에서 제외)\n"

        last_claims = claims.get("last_claims", [])
        if last_claims:
            part += "\n[등록 청구항]\n"
            for c in last_claims:
                text = (c.get("text") or "").strip()
                if not text:
                    continue
                cnum = c.get("claim_number", "?")
                ctype = c.get("claim_type", "")
                if len(text) > MAX_CLAIM_LEN:
                    text = text[:MAX_CLAIM_LEN] + "..."
                part += f"  제{cnum}항 ({ctype}): {text}\n"

        parts.append(part)

    return "\n".join(parts)


def _print_search_summary(results: list[dict]):
    """검색 결과 요약 출력."""
    print(f"  {len(results)}개 특허 검색됨")
    for i, r in enumerate(results[:MAX_PATENTS]):
        meta = r.get("metadata", {})
        title = meta.get("invention_title", "?")[:50]
        pid = r.get("patent_id", "?")
        regit = meta.get("regit_num", "?")
        score = r.get("score", 0)
        claim = r.get("matched_claim_num", "?")
        print(f"    {i + 1}. [{score:.4f}] 제{claim}항 - {title}")
        print(f"       출원: {pid} | 등록: {regit}")


# ── 세션 기록 ────────────────────────────────────────

session_log = []


def _record_turn(turn_type: str, user_input: str, search_query: str,
                 search_results: list[dict] | None, assistant_msg: str,
                 search_elapsed: float, llm_elapsed: float):
    """대화 턴을 세션 로그에 추가."""
    search_summary = []
    if search_results:
        for i, r in enumerate(search_results[:MAX_PATENTS], 1):
            meta = r.get("metadata", {})
            search_summary.append({
                "rank": i,
                "patent_id": r.get("patent_id", ""),
                "regit_num": meta.get("regit_num", ""),
                "invention_title": meta.get("invention_title", ""),
                "score": round(r.get("score", 0), 6),
                "matched_claim_num": r.get("matched_claim_num", 0),
                "estoppel_claim_numbers": r.get("estoppel_claim_numbers", []),
            })

    session_log.append({
        "turn_num": len(session_log) + 1,
        "timestamp": datetime.now(KST).strftime("%H:%M:%S"),
        "turn_type": turn_type,
        "user_input": user_input,
        "search_query": search_query if search_query != user_input else None,
        "search_elapsed_sec": round(search_elapsed, 3) if search_elapsed else None,
        "llm_elapsed_sec": round(llm_elapsed, 3),
        "search_results": search_summary if search_summary else None,
        "assistant_response": assistant_msg,
    })


def _save_session():
    """세션 로그를 JSON + MD로 저장."""
    if not session_log:
        print("  저장할 대화 기록이 없습니다.")
        return

    now = datetime.now(KST)
    file_stem = now.strftime("%Y%m%d_%H%M")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # JSON 저장
    session_data = {
        "date": now.strftime("%Y-%m-%d"),
        "session_start": session_log[0]["timestamp"],
        "session_end": now.strftime("%H:%M:%S"),
        "model": "gpt-4o-mini",
        "total_turns": len(session_log),
        "turns": session_log,
    }

    json_path = REPORT_DIR / f"{file_stem}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)

    # MD 저장
    md_path = REPORT_DIR / f"{file_stem}.md"
    md_lines = _build_md_report(session_data)
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"\n  대화 기록 저장 완료:")
    print(f"    JSON: {json_path}")
    print(f"    MD:   {md_path}")


def _build_md_report(data: dict) -> list[str]:
    """세션 데이터를 마크다운 보고서로 변환."""
    lines = []
    lines.append("# 챗봇 테스트 대화 기록")
    lines.append("")
    lines.append(f"> 날짜: {data['date']} | 세션: {data['session_start']} ~ {data['session_end']} | 모델: {data['model']}")
    lines.append("")

    for t in data["turns"]:
        lines.append(f"### 턴 {t['turn_num']} ({t['timestamp']}) — {t['turn_type']}")
        lines.append("")
        lines.append(f"**사용자:** {t['user_input']}")
        lines.append("")

        if t.get("search_results"):
            lines.append(f"**검색 결과** ({t['search_elapsed_sec']}s):")
            lines.append("")
            lines.append("| 순위 | 등록번호 | 점수 | 매칭항 | 제목 |")
            lines.append("|------|----------|------|--------|------|")
            for r in t["search_results"]:
                title = r["invention_title"][:40]
                if len(r["invention_title"]) > 40:
                    title += "..."
                est = f" [금반언:{r['estoppel_claim_numbers']}]" if r["estoppel_claim_numbers"] else ""
                lines.append(
                    f"| {r['rank']} | `{r['regit_num']}` | {r['score']} "
                    f"| 제{r['matched_claim_num']}항 | {title}{est} |"
                )
            lines.append("")

        lines.append(f"**GPT 응답** ({t['llm_elapsed_sec']}s):")
        lines.append("")
        lines.append(t["assistant_response"])
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("*이 보고서는 챗봇 테스트 세션에서 자동 생성되었습니다.*")
    return lines


# ── 챗봇 REPL ────────────────────────────────────────

def run():
    """챗봇 REPL 실행. 제품 설명 → 특허 검색 → GPT 침해 분석 → 후속 대화."""
    api_key = os.environ.get("OPENAI_API_KEY", "") or config.OPENAI_API_KEY
    if not api_key:
        print("OPENAI_API_KEY가 설정되지 않았습니다.")
        print("  프로젝트 루트의 .env 파일에 OPENAI_API_KEY=sk-... 를 추가하세요.")
        return

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    has_searched = False          # 이전에 검색한 적 있는지 (후속질문 판별용)
    last_search_results = None    # 마지막 검색 결과 (세션 로그용)

    print("=" * 60)
    print("FTO 특허 침해 분석 챗봇 (테스트용)")
    print("-" * 60)
    print("  제품 설명을 입력하면 특허 검색 + 침해 분석을 수행합니다")
    print("  이후 후속 질문은 이전 검색 결과를 기반으로 답변합니다")
    print()
    print("  명령어:")
    print("    /search <쿼리>  새로운 제품으로 검색")
    print("    /report         현재까지 대화 기록 저장")
    print("    /clear          대화 초기화")
    print("    q, quit         종료 (자동 저장)")
    print(f"  종료 시 자동 저장: {REPORT_DIR}")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n사용자> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            _save_session()
            print("종료.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("q", "quit", "exit"):
            _save_session()
            print("종료.")
            break
        if user_input.lower() == "/clear":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            has_searched = False
            last_search_results = None
            print("  대화가 초기화되었습니다.")
            continue
        if user_input.lower() == "/report":
            _save_session()
            continue

        # 검색 여부 판별:
        #   /search 명령어 → 새 검색
        #   첫 메시지 (검색 이력 없음) → 새 검색
        #   그 외 (이미 검색한 적 있음) → 후속질문 (검색 안 함)
        do_search = False
        search_query = user_input

        if user_input.startswith("/search "):
            do_search = True
            search_query = user_input[8:].strip()
        elif not has_searched:
            do_search = True

        turn_start = time.time()

        # RAG 파이프라인으로 관련 특허 검색
        search_results = None
        search_elapsed = 0.0
        if do_search and search_query:
            print(f"\n  검색 중: {search_query}")
            search_start = time.time()
            search_results = search(search_query, verbose=False)
            search_elapsed = time.time() - search_start

            _print_search_summary(search_results)
            print(f"  검색 시간: {search_elapsed:.3f}s")

            has_searched = True
            last_search_results = search_results

            if search_results:
                results_text = _format_search_results(search_results)
                user_message = (
                    f"[사용자 제품 설명]\n{search_query}\n\n"
                    f"[검색된 특허]\n{results_text}\n\n"
                    f"위 특허들을 기반으로 사용자 제품의 침해 여부를 분석해주세요."
                )
            else:
                user_message = (
                    f"[사용자 제품 설명]\n{search_query}\n\n"
                    f"[검색 결과]\n관련 특허를 찾지 못했습니다.\n\n"
                    f"검색된 특허가 없으므로, 현재 데이터베이스 기준으로 "
                    f"특허 침해 가능성이 발견되지 않았다고 안내해주세요."
                )
        else:
            # 후속질문: 검색 없이 이전 대화 맥락으로 답변
            user_message = user_input

        messages.append({"role": "user", "content": user_message})

        # OpenAI GPT-4o-mini 호출 (temperature=0.3으로 안정적 분석)
        print("\n  분석 중...")
        llm_start = time.time()
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.3,
                max_tokens=2000,
            )
            llm_elapsed = time.time() - llm_start
            total_elapsed = time.time() - turn_start
            assistant_msg = response.choices[0].message.content
            messages.append({"role": "assistant", "content": assistant_msg})

            print(f"\n{'─' * 60}")
            print(assistant_msg)
            print(f"{'─' * 60}")
            # 총 소요 시간 표시
            if do_search:
                print(f"  검색: {search_elapsed:.3f}s | LLM: {llm_elapsed:.3f}s | 총: {total_elapsed:.3f}s")
            else:
                print(f"  LLM: {llm_elapsed:.3f}s | 총: {total_elapsed:.3f}s")

            # 세션 로그에 기록
            turn_type = "검색+분석" if do_search else "후속질문"
            _record_turn(
                turn_type=turn_type,
                user_input=user_input,
                search_query=search_query if do_search else user_input,
                search_results=search_results,
                assistant_msg=assistant_msg,
                search_elapsed=search_elapsed if do_search else 0.0,
                llm_elapsed=llm_elapsed,
            )
        except Exception as e:
            print(f"\n  [오류] LLM 호출 실패: {e}")
            messages.pop()


if __name__ == "__main__":
    run()
