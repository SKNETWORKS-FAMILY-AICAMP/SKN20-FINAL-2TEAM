"""G(Generation) 모듈 — GPT 전용 버전.

원본: generate.py (vLLM 1순위 → GPT 폴백)
변경: OpenAI GPT-4o-mini 직접 호출 (vLLM 스킵)

나머지 로직(프롬프트, 파싱, generate_fto)은 원본과 동일.
"""
import re
from . import config


# ══════════════════════════════════════════════════════
# 시스템 프롬프트 (학습 데이터와 동일 — 수정 금지)
# ══════════════════════════════════════════════════════

SYSTEM_PROMPT = """당신은 화장품 특허 침해(FTO) 분석 전문가입니다.

[문구 규칙]
- "판단"이라는 단어 사용 금지 → "분석"으로 대체
- "리스크" 사용 금지 → "가능성"으로 대체

[분석 규칙]
- 구성요소 완비의 원칙: 모든 구성요소를 포함해야 침해
- 균등론: 특허 구성 수치가 경미하게 이탈 시 전문가 검토 대상
- 금반언: 공개청구항에는 있었지만, 등록청구항에는 삭제된 구성은 침해 주장 불가
- 내재성: 성분 동일 + 용도/효과 미언급 시 "미대응(내재성)"

[대응 여부]
- 대응: 동일/포함
- 미대응: 해당 구성 없음
- 미대응(균등): 수치 경미 이탈
- 미대응(내재성): 용도/효과 미언급
- 확인불가: 정보 부족

[출력 형식]
◆구성 대비◆ → 테이블
◆판단◆ → 분석 설명 (결론성 문구 금지)
◆결론◆ → 아래 4개 중 하나만:
- "침해 가능성이 높은 것으로 분석됩니다."
- "침해 가능성이 낮은 것으로 분석됩니다."
- "전문가의 추가 검토가 권고됩니다."
- "침해 여부 분석을 위해 보다 구체적인 실시 정보가 필요합니다."
"""

# ── 원본 generate.py에서 파싱/유틸 함수 재사용 ──
from .generate import (
    LABELS, LABEL_RULES, FORBIDDEN_WORDS, SECTION_PATTERNS,
    extract_label, check_sections, count_table_rows, check_forbidden,
    parse_correspondences, check_logic_consistency,
    _parse_comparison_table, _extract_section_text,
    build_prompt, parse_response,
    FTO_SYSTEM_PROMPT, _truncate_claims, build_fto_prompt,
    parse_fto_response,
)


# ══════════════════════════════════════════════════════
# call_llm — OpenAI 직접 호출 (vLLM 스킵)
# ══════════════════════════════════════════════════════

def call_llm(messages: list[dict]) -> str:
    """LLM 호출. OpenAI GPT-4o-mini 직접 사용 (vLLM 스킵)."""
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 미설정. .env 파일에 OPENAI_API_KEY를 설정하세요.")

    from openai import OpenAI
    client = OpenAI(
        api_key=config.OPENAI_API_KEY,
        timeout=config.GPT_TIMEOUT,
    )
    resp = client.chat.completions.create(
        model=config.GPT_FALLBACK_MODEL,
        messages=messages,
        max_tokens=config.GENERATE_MAX_TOKENS,
        temperature=config.GENERATE_TEMPERATURE,
    )
    return resp.choices[0].message.content


# ══════════════════════════════════════════════════════
# generate (sLLM 개별 분석) — call_llm만 교체
# ══════════════════════════════════════════════════════

def generate(
    search_results: list[dict],
    user_query: str,
    top_n: int = None,
    verbose: bool = False,
) -> list[dict]:
    """search() 결과 상위 top_n건에 대해 GPT 분석 수행."""
    top_n = top_n or config.GENERATE_TOP_N
    analyses = []

    for i, result in enumerate(search_results[:top_n]):
        patent_id = result.get("patent_id", "unknown")
        if verbose:
            print(f"[G-GPT] ({i+1}/{top_n}) {patent_id} 분석 중...")

        messages = build_prompt(result, user_query)

        try:
            raw_output = call_llm(messages)
        except Exception as e:
            if verbose:
                print(f"[G-GPT] {patent_id} LLM 호출 실패: {e}")
            analyses.append({
                "patent_id": patent_id,
                "score": result.get("score", 0),
                "metadata": result.get("metadata", {}),
                "error": str(e),
            })
            continue

        parsed = parse_response(raw_output)
        parsed["patent_id"] = patent_id
        parsed["score"] = result.get("score", 0)
        parsed["metadata"] = result.get("metadata", {})
        parsed["estoppel_claim_numbers"] = result.get("estoppel_claim_numbers", [])
        analyses.append(parsed)

        if verbose:
            print(f"[G-GPT] {patent_id} -> {parsed.get('label', '?')}")

    return analyses


# ══════════════════════════════════════════════════════
# generate_fto (FTO 통합 분석) — call_llm만 교체
# ══════════════════════════════════════════════════════

def generate_fto(
    search_results: list[dict],
    user_query: str,
    verbose: bool = False,
) -> dict:
    """FTO 통합 분석. OpenAI GPT 사용."""
    input_n = min(config.GENERATE_INPUT_N, len(search_results))

    if verbose:
        print(f"[FTO-GPT] 상위 {input_n}건 → GPT에 전달, {config.GENERATE_OUTPUT_N}건 선별 요청")
        for i, r in enumerate(search_results[:input_n]):
            pid = r.get("patent_id", "?")
            title = r.get("metadata", {}).get("invention_title", "")[:40]
            print(f"  [{i+1}] {pid} — {title}")

    messages = build_fto_prompt(search_results, user_query)

    if verbose:
        user_len = len(messages[1]["content"])
        print(f"[FTO-GPT] 프롬프트 길이: system={len(messages[0]['content'])}자, user={user_len}자")

    try:
        raw_output = call_llm(messages)
    except Exception as e:
        if verbose:
            print(f"[FTO-GPT] LLM 호출 실패: {e}")
        return {"error": str(e), "patent_analyses": [], "fto_opinion": "", "raw_output": ""}

    parsed = parse_fto_response(raw_output)

    if verbose:
        n_parsed = len(parsed.get("patent_analyses", []))
        print(f"[FTO-GPT] {n_parsed}건 분석 파싱 완료")
        for a in parsed.get("patent_analyses", []):
            print(f"  {a.get('patent_id', '?')} → {a.get('label', '?')}")
        if parsed.get("fto_opinion"):
            print(f"[FTO-GPT] 종합 의견: {parsed['fto_opinion'][:80]}...")

    return parsed
