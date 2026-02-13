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

사용법:
    python -m v1.rag.eval.chatbot.run
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# .env 파일에서 OPENAI_API_KEY 로드
load_dotenv(project_root / ".env")

from v1.rag import config
from v1.rag.pipeline import search

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
        score = r.get("score", 0)
        claim = r.get("matched_claim_num", "?")
        print(f"    {i + 1}. [{score:.4f}] 제{claim}항 - {title}")


# ── 챗봇 REPL ────────────────────────────────────────

def run():
    api_key = os.environ.get("OPENAI_API_KEY", "") or config.OPENAI_API_KEY
    if not api_key:
        print("OPENAI_API_KEY가 설정되지 않았습니다.")
        print("  프로젝트 루트의 .env 파일에 OPENAI_API_KEY=sk-... 를 추가하세요.")
        return

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    has_searched = False

    print("=" * 60)
    print("BINI 특허 침해 분석 챗봇 (테스트용)")
    print("-" * 60)
    print("  제품 설명을 입력하면 특허 검색 + 침해 분석을 수행합니다")
    print()
    print("  명령어:")
    print("    /search <쿼리>  새로운 제품으로 검색")
    print("    /clear          대화 초기화")
    print("    q, quit         종료")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n사용자> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("q", "quit", "exit"):
            print("종료.")
            break
        if user_input.lower() == "/clear":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            has_searched = False
            print("  대화가 초기화되었습니다.")
            continue

        # 검색 여부 판단
        do_search = False
        search_query = user_input

        if user_input.startswith("/search "):
            do_search = True
            search_query = user_input[8:].strip()
        elif not has_searched:
            do_search = True

        # 검색 실행
        if do_search and search_query:
            print(f"\n  검색 중: {search_query}")
            results = search(search_query, verbose=False)
            has_searched = True

            _print_search_summary(results)

            results_text = _format_search_results(results)
            user_message = (
                f"[사용자 제품 설명]\n{search_query}\n\n"
                f"[검색된 특허]\n{results_text}\n\n"
                f"위 특허들을 기반으로 사용자 제품의 침해 여부를 분석해주세요."
            )
        else:
            user_message = user_input

        messages.append({"role": "user", "content": user_message})

        # LLM 호출
        print("\n  분석 중...")
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.3,
                max_tokens=2000,
            )
            assistant_msg = response.choices[0].message.content
            messages.append({"role": "assistant", "content": assistant_msg})

            print(f"\n{'─' * 60}")
            print(assistant_msg)
            print(f"{'─' * 60}")
        except Exception as e:
            print(f"\n  [오류] LLM 호출 실패: {e}")
            messages.pop()


if __name__ == "__main__":
    run()
