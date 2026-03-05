"""G(Generation) 모듈. RAG 검색 결과를 LLM에 넘겨 침해 분석 리포트를 생성한다.

두 가지 모드:
    [FTO 통합] generate_fto(): Top 5를 한번에 GPT에 전달 → 3건 선별 + 종합 의견 (현재 활성)
    [sLLM 개별] generate():    Top N을 1건씩 sLLM 호출 → 개별 분석 리포트 (sLLM 복귀 시 사용)

관계:
    - pipeline.py의 search() 결과를 입력으로 받음
    - pipeline.py의 analyze()가 generate_fto()를 호출
    - backend_adapter.py가 pipeline.analyze()를 래핑
"""
import re
from . import config

# ══════════════════════════════════════════════════════
# 시스템 프롬프트 (학습 데이터와 동일 — 수정 금지)
# 출처: SLLM_model/training/train_qwen_v2.py L56~83
# 이 프롬프트로 17,377건을 학습했으므로 한 글자라도 바뀌면 성능 저하 가능
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


# ══════════════════════════════════════════════════════
# 라벨/파싱 상수 + 유틸 함수 (common.py에서 이식)
# 출처: SLLM_model/sllm_all_train_dj/eval/common.py
# ══════════════════════════════════════════════════════

LABELS = ["침해", "비침해", "애매", "침해_전문가"]

LABEL_RULES = [
    ("전문가", "침해_전문가"),
    ("구체적인 실시 정보", "애매"),
    ("추가 정보", "애매"),
    ("가능성이 낮", "비침해"),
    ("속하지 않을", "비침해"),
    ("가능성이 높", "침해"),
]

FORBIDDEN_WORDS = ["판단됩니다", "판단합니다", "판단되므로", "리스크"]

SECTION_PATTERNS = {
    "구성 대비": re.compile(r"◆\s*구성\s*대비\s*◆"),
    "판단": re.compile(r"◆\s*(?:판단|분석)\s*◆"),
    "결론": re.compile(r"◆\s*결론\s*◆"),
}


def _extract_conclusion(text: str) -> str:
    """결론 섹션만 추출. 없으면 전체 텍스트 반환."""
    if not isinstance(text, str):
        return ""
    match = SECTION_PATTERNS["결론"].search(text)
    if match:
        return text[match.end():]
    return text


def extract_label(text: str) -> str:
    """모델 출력의 결론 섹션에서 키워드 기반 라벨 매핑.

    우선순위: 전문가 -> 애매 -> 비침해 -> 침해
    """
    conclusion = _extract_conclusion(text)
    if not conclusion:
        return "매핑실패"
    for keyword, label in LABEL_RULES:
        if keyword in conclusion:
            return label
    return "매핑실패"


def check_sections(text: str) -> dict[str, bool]:
    """구성 대비, 판단, 결론 존재 여부."""
    if not isinstance(text, str):
        return {s: False for s in SECTION_PATTERNS}
    return {name: bool(pat.search(text)) for name, pat in SECTION_PATTERNS.items()}


def count_table_rows(text: str) -> int:
    """마크다운 테이블 데이터 행 수 (헤더/구분선 제외)."""
    if not isinstance(text, str):
        return 0
    count = 0
    found_sep = False
    for line in text.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            if found_sep:
                break
            continue
        if re.match(r"^\|[\s\-:|]+\|$", s):
            found_sep = True
            continue
        if found_sep:
            count += 1
    return count


def check_forbidden(text: str) -> list[str]:
    """금지 문구 포함 여부."""
    if not isinstance(text, str):
        return []
    return [w for w in FORBIDDEN_WORDS if w in text]


def parse_correspondences(text: str) -> list[str]:
    """구성대비표에서 대응여부 값 추출.

    테이블 3번째 컬럼(대응여부)을 파싱한다.
    예: ["대응", "대응", "미대응", "미대응(균등)"]
    """
    if not isinstance(text, str):
        return []
    values = []
    found_sep = False
    for line in text.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            if found_sep:
                break
            continue
        if re.match(r"^\|[\s\-:|]+\|$", s):
            found_sep = True
            continue
        if found_sep:
            cells = [c.strip() for c in s.split("|")]
            cells = [c for c in cells if c]
            if len(cells) >= 3:
                values.append(cells[2])
    return values


def check_logic_consistency(pred_label: str, pred_output: str) -> str:
    """법리 일관성 체크. 라벨과 대응분석표의 논리적 정합성 검증.

    규칙 9:  침해 + 일반 미대응 -> 비침해여야 함
    규칙 10: 비침해 + 전부 대응 -> 침해여야 함
    규칙 11: 침해_전문가 + 균등/내재성 없음 -> 근거 없음
    규칙 12: 침해 + 균등/내재성 있음 -> 침해_전문가여야 함
    규칙 13: 침해_전문가 + 일반 미대응 있음 -> 비침해여야 함
    규칙 14: 비침해 + 균등/내재성만 (일반 미대응 없음) -> 침해_전문가여야 함

    Returns:
        "O"  = 일관성 있음
        "X:규칙번호:사유" = 불일치
        "-"  = 체크 불가 (애매/매핑실패 또는 테이블 파싱 불가)
    """
    if pred_label in ("애매", "매핑실패"):
        return "-"

    corrs = parse_correspondences(pred_output)
    if not corrs:
        return "-"

    # 규칙 9: 침해인데 일반 미대응 존재 -> 비침해여야 함
    if pred_label == "침해":
        has_plain_mismatch = any(c.strip() == "미대응" for c in corrs)
        if has_plain_mismatch:
            return "X:R9:침해+일반미대응"

    # 규칙 10: 비침해인데 전부 대응 -> 침해여야 함
    if pred_label == "비침해":
        all_match = all(c.strip() == "대응" for c in corrs)
        if all_match:
            return "X:R10:비침해+전부대응"

    # 규칙 11: 침해_전문가인데 균등/내재성 없음 -> 근거 없음
    if pred_label == "침해_전문가":
        has_special = any("균등" in c or "내재성" in c for c in corrs)
        if not has_special:
            return "X:R11:전문가+균등내재성없음"

    # 규칙 12: 침해인데 균등/내재성 있음 -> 침해_전문가여야 함
    if pred_label == "침해":
        has_special = any("균등" in c or "내재성" in c for c in corrs)
        if has_special:
            return "X:R12:침해+균등내재성존재"

    # 규칙 13: 침해_전문가인데 일반 미대응 있음 -> 비침해여야 함
    if pred_label == "침해_전문가":
        has_plain = any(c.strip() == "미대응" for c in corrs)
        if has_plain:
            return "X:R13:전문가+일반미대응"

    # 규칙 14: 비침해인데 균등/내재성만 있음 (일반 미대응 없음) -> 침해_전문가여야 함
    if pred_label == "비침해":
        has_plain = any(c.strip() == "미대응" for c in corrs)
        has_special = any("균등" in c or "내재성" in c for c in corrs)
        if has_special and not has_plain:
            return "X:R14:비침해+균등내재성만"

    return "O"


# ══════════════════════════════════════════════════════
# 신규 헬퍼 함수
# ══════════════════════════════════════════════════════

def _parse_comparison_table(text: str) -> list[dict]:
    """구성 대비 마크다운 테이블 -> list[dict] 파싱."""
    if not isinstance(text, str):
        return []
    comparisons = []
    found_sep = False
    for line in text.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            if found_sep:
                break
            continue
        if re.match(r"^\|[\s\-:|]+\|$", s):
            found_sep = True
            continue
        if found_sep:
            cells = [c.strip() for c in s.split("|")]
            cells = [c for c in cells if c]
            if len(cells) >= 3:
                comparisons.append({
                    "patent_element": cells[0],
                    "user_element": cells[1],
                    "correspondence": cells[2],
                })
    return comparisons


def _extract_section_text(text: str, start_section: str, end_section: str | None) -> str:
    """두 섹션 마커 사이의 텍스트를 추출한다."""
    if not isinstance(text, str):
        return ""
    start_pat = SECTION_PATTERNS.get(start_section)
    if not start_pat:
        return ""
    start_match = start_pat.search(text)
    if not start_match:
        return ""
    start_pos = start_match.end()
    if end_section and end_section in SECTION_PATTERNS:
        end_pat = SECTION_PATTERNS[end_section]
        end_match = end_pat.search(text, start_pos)
        if end_match:
            return text[start_pos:end_match.start()].strip()
    return text[start_pos:].strip()


# ══════════════════════════════════════════════════════
# 공개 함수 1: build_prompt
# ══════════════════════════════════════════════════════

def build_prompt(search_result: dict, user_query: str) -> list[dict]:
    """search() 결과 1건 + 사용자 쿼리 -> sLLM chat messages.

    Args:
        search_result: pipeline.search() 반환 리스트의 원소 1건.
        user_query: 사용자 원본 쿼리 (제품 설명).

    Returns:
        OpenAI chat 형식 messages (system + user).
    """
    parts = []

    # 사용자 쿼리
    parts.append(user_query)

    # [구성요소] — claim_components 테이블에서 사전 추출된 구성요소
    components_list = search_result.get("components", [])
    if components_list:
        comp_texts = []
        for comp in components_list:
            comp_text = comp.get("components", "")
            if comp_text:
                comp_texts.append(comp_text)
        if comp_texts:
            parts.append(f"\n[구성요소]\n" + "\n\n".join(comp_texts))

    # [등록 청구항] — parents.sqlite 원문 직접 사용
    claim_regit = search_result.get("claims", {}).get("claim_regit_text", "")
    if claim_regit:
        parts.append(f"\n[등록 청구항]\n{claim_regit}")

    # [공개 청구항] — parents.sqlite 원문 직접 사용
    claim_pub = search_result.get("claims", {}).get("claim_pub_text", "")
    if claim_pub:
        parts.append(f"\n[공개 청구항]\n{claim_pub}")

    # [특허 정보]
    meta = search_result.get("metadata", {})
    meta_parts = []
    for key, name in [("apply_num", "출원번호"), ("regit_num", "등록번호")]:
        val = meta.get(key, "")
        if val:
            meta_parts.append(f"{name}: {val}")
    if meta_parts:
        parts.append(f"\n[특허 정보]\n" + "\n".join(meta_parts))

    # 출력 형식 힌트 (SYSTEM_PROMPT 변경 없이 유도)
    parts.append(
        "\n[출력 형식]\n"
        "반드시 한국어로만 출력하시오.\n"
        "◆구성 대비◆\n"
        "| 특허 구성요소 | 사용자 제품 구성요소 | 대응 여부 |\n"
        "|---|---|---|"
    )

    user_content = "\n".join(parts)

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ══════════════════════════════════════════════════════
# 공개 함수 2: call_llm
# ══════════════════════════════════════════════════════

def call_llm(messages: list[dict]) -> str:
    """LLM 호출. vLLM 전용 (보안 정책: 외부 API 폴백 비활성화)."""
    if not config.VLLM_API_URL:
        raise RuntimeError(
            "[rag] VLLM_API_URL 미설정. .env 파일을 확인하세요."
        )
    return _call_vllm(messages)

    # GPT 폴백 (보안 정책: 비활성화 — 외부 API로 데이터 유출 방지)
    # if config.OPENAI_API_KEY:
    #     return _call_openai(messages)


def _call_vllm(messages: list[dict]) -> str:
    """vLLM OpenAI-compatible API 호출 (RunPod 서버리스 또는 로컬)."""
    from openai import OpenAI

    # RunPod 서버리스인 경우 API Key 사용
    api_key = config.RUNPOD_API_KEY if config.RUNPOD_API_KEY else "dummy"

    client = OpenAI(
        base_url=config.VLLM_API_URL,
        api_key=api_key,
        timeout=config.VLLM_TIMEOUT,
    )
    resp = client.chat.completions.create(
        model=config.VLLM_MODEL_NAME,
        messages=messages,
        max_tokens=config.GENERATE_MAX_TOKENS,
        temperature=config.GENERATE_TEMPERATURE,
    )
    if not resp.choices:
        raise RuntimeError(f"[rag] vLLM 응답에 choices가 없습니다: {resp}")
    return resp.choices[0].message.content or ""


# GPT 폴백 (보안 정책: 비활성화 — 외부 API로 데이터 유출 방지)
# def _call_openai(messages: list[dict]) -> str:
#     """GPT-4o-mini OpenAI API 호출."""
#     from openai import OpenAI
#     client = OpenAI(
#         api_key=config.OPENAI_API_KEY,
#         timeout=config.GPT_TIMEOUT,
#     )
#     resp = client.chat.completions.create(
#         model=config.GPT_FALLBACK_MODEL,
#         messages=messages,
#         max_tokens=config.GENERATE_MAX_TOKENS,
#         temperature=config.GENERATE_TEMPERATURE,
#     )
#     return resp.choices[0].message.content


# ══════════════════════════════════════════════════════
# 공개 함수 3: parse_response
# ══════════════════════════════════════════════════════

_REPETITION_THRESHOLD = 20  # 동일 패턴 반복 횟수 임계값


def _has_excessive_repetition(text: str) -> bool:
    """동일 패턴(2글자 이상)이 _REPETITION_THRESHOLD회 이상 반복되는지 검사."""
    if not text or len(text) < 100:
        return False
    for length in (2, 3, 4):
        counts: dict[str, int] = {}
        for i in range(len(text) - length + 1):
            chunk = text[i:i + length]
            if chunk.strip():
                counts[chunk] = counts.get(chunk, 0) + 1
                if counts[chunk] >= _REPETITION_THRESHOLD:
                    return True
    return False


_FALLBACK_ANALYSIS_TEXT = "AI 자동 분석이 어려운 특허입니다. 해당 특허는 전문가의 직접 검토를 권장합니다."


def parse_response(raw_text: str) -> dict:
    """sLLM 출력 -> 구조화 JSON."""
    result = {"raw_output": raw_text}
    result["sections_found"] = check_sections(raw_text)
    result["comparisons"] = _parse_comparison_table(raw_text)
    result["table_row_count"] = count_table_rows(raw_text)
    result["analysis_text"] = _extract_section_text(raw_text, "판단", "결론")
    result["label"] = extract_label(raw_text)
    result["conclusion_text"] = _extract_section_text(raw_text, "결론", None)
    result["logic_consistency"] = check_logic_consistency(result["label"], raw_text)
    result["forbidden_words"] = check_forbidden(raw_text)

    # 출력 검증: 쓰레기 출력 감지 → 분석불가 처리
    is_garbage = (
        not result["sections_found"].get("구성 대비", False)
        or result["table_row_count"] == 0
        or _has_excessive_repetition(raw_text)
    )
    if is_garbage:
        result["label"] = "분석불가"
        result["comparisons"] = []
        result["analysis_text"] = _FALLBACK_ANALYSIS_TEXT
        result["conclusion_text"] = _FALLBACK_ANALYSIS_TEXT

    return result


# ══════════════════════════════════════════════════════
# 공개 함수 4: generate (진입점)
# ══════════════════════════════════════════════════════

def generate(
    search_results: list[dict],
    user_query: str,
    top_n: int = None,
    verbose: bool = False,
) -> list[dict]:
    """search() 결과 상위 top_n건에 대해 sLLM 분석 수행.

    Args:
        search_results: pipeline.search() 반환값.
        user_query: 사용자 원본 쿼리.
        top_n: 분석할 특허 수 (기본: config.GENERATE_TOP_N).
        verbose: 중간 로그 출력.

    Returns:
        특허별 분석 결과 리스트.
    """
    top_n = top_n or config.GENERATE_TOP_N
    analyses = []

    for i, result in enumerate(search_results[:top_n]):
        patent_id = result.get("patent_id", "unknown")
        if verbose:
            print(f"[G] ({i+1}/{top_n}) {patent_id} 분석 중...")

        messages = build_prompt(result, user_query)

        try:
            raw_output = call_llm(messages)
        except Exception as e:
            if verbose:
                print(f"[G] {patent_id} LLM 호출 실패: {e}")
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
            print(f"[G] {patent_id} -> {parsed.get('label', '?')}")

    return analyses


# ══════════════════════════════════════════════════════
# FTO 통합 분석 (GPT 전용 — sLLM 미사용)
# ══════════════════════════════════════════════════════

FTO_SYSTEM_PROMPT = f"""당신은 화장품 특허 침해(FTO: Freedom To Operate) 분석 전문가입니다.

사용자가 출시하려는 제품 설명과 관련 특허 {config.GENERATE_INPUT_N}건이 주어집니다.
이 중 침해 가능성이 높은 특허 {config.GENERATE_OUTPUT_N}건을 선별하여 분석하세요.

[문구 규칙]
- "판단"이라는 단어 사용 금지 → "분석"으로 대체
- "리스크" 사용 금지 → "가능성"으로 대체

[분석 규칙]
- 구성요소 완비의 원칙: 모든 구성요소를 포함해야 침해
- 균등론: 특허 구성 수치가 경미하게 이탈 시 전문가 검토 대상
- 금반언: 공개청구항에는 있었지만 등록청구항에서 삭제된 구성은 침해 주장 불가
- 내재성: 성분 동일 + 용도/효과 미언급 시 "미대응(내재성)"

[대응 여부]
- 대응: 동일/포함
- 미대응: 해당 구성 없음
- 미대응(균등): 수치 경미 이탈
- 미대응(내재성): 용도/효과 미언급
- 확인불가: 정보 부족

[출력 형식]
선별한 특허 {config.GENERATE_OUTPUT_N}건 각각에 대해 아래 형식으로 작성하세요:

## 특허 N: [등록번호 또는 출원번호]
◆구성 대비◆
| 특허 구성요소 | 제품 구성요소 | 대응 여부 |
|---|---|---|
(등록 청구항의 구성요소별 대비)

◆판단◆
(분석 설명 — 결론성 문구 금지)

◆결론◆
아래 4개 중 하나만:
- "침해 가능성이 높은 것으로 분석됩니다."
- "침해 가능성이 낮은 것으로 분석됩니다."
- "전문가의 추가 검토가 권고됩니다."
- "침해 여부 분석을 위해 보다 구체적인 실시 정보가 필요합니다."

{config.GENERATE_OUTPUT_N}건 분석 후 마지막에:

◆종합 FTO 의견◆
(제품 출시 관점에서 전체적인 침해 가능성 요약 및 권고사항)
"""


def _truncate_claims(text: str, max_chars: int = 3000) -> str:
    """청구항 텍스트를 max_chars 이내로 잘라서 토큰 초과 방지."""
    if not text or len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... (이하 생략)"


def build_fto_prompt(search_results: list[dict], user_query: str, history: list[dict] = None) -> list[dict]:
    """search() 결과 여러 건 + 사용자 쿼리 -> GPT chat messages.

    Args:
        search_results: pipeline.search() 반환 리스트 (상위 N건).
        user_query: 사용자 원본 쿼리 (제품 설명).
        history: 이전 대화 히스토리 [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        OpenAI chat 형식 messages (system + history + user).
    """
    top_n = config.GENERATE_INPUT_N
    results = search_results[:top_n]

    parts = [f"[사용자 제품]\n{user_query}"]

    for i, result in enumerate(results):
        meta = result.get("metadata", {})
        patent_parts = []

        # 특허 헤더
        apply_num = meta.get("apply_num", result.get("patent_id", "?"))
        regit_num = meta.get("regit_num", "")
        title = meta.get("invention_title", "")
        patent_parts.append(f"\n[특허 {i+1}]")
        patent_parts.append(f"출원번호: {apply_num}" + (f" | 등록번호: {regit_num}" if regit_num else ""))
        if title:
            patent_parts.append(f"발명 명칭: {title}")

        # 초록
        abstract = meta.get("abstract", "")
        if abstract:
            patent_parts.append(f"초록: {abstract}")

        # 금반언 청구항
        estoppel = result.get("estoppel_claim_numbers", [])
        if estoppel:
            patent_parts.append(f"금반언 청구항: {estoppel} (삭제됨 - 침해 주장 불가)")

        # [구성요소] — claim_components 테이블에서 사전 추출된 구성요소
        components_list = result.get("components", [])
        if components_list:
            comp_texts = []
            for comp in components_list:
                comp_text = comp.get("components", "")
                if comp_text:
                    comp_texts.append(comp_text)
            if comp_texts:
                joined = "\n\n".join(comp_texts)
                patent_parts.append(f"[구성요소]\n{_truncate_claims(joined)}")

        # 등록 청구항 — parents.sqlite 원문 직접 사용 (토큰 초과 방지를 위해 잘라냄)
        claim_regit = result.get("claims", {}).get("claim_regit_text", "")
        if claim_regit:
            patent_parts.append(f"[등록 청구항]\n{_truncate_claims(claim_regit)}")

        # 공개 청구항 — parents.sqlite 원문 직접 사용 (토큰 초과 방지를 위해 잘라냄)
        claim_pub = result.get("claims", {}).get("claim_pub_text", "")
        if claim_pub:
            patent_parts.append(f"[공개 청구항]\n{_truncate_claims(claim_pub)}")

        parts.append("\n".join(patent_parts))

    user_content = "\n".join(parts)

    # 메시지 구성: system + history + current user
    messages = [{"role": "system", "content": FTO_SYSTEM_PROMPT}]

    # 이전 대화 히스토리 추가 (멀티턴 지원)
    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": user_content})

    return messages


def parse_fto_response(raw_text: str) -> dict:
    """FTO 통합 응답 파싱. 특허별 섹션 분리 + 종합 의견 추출.

    Returns:
        {
            "raw_output": str,
            "patent_analyses": [
                {"patent_id": str, "label": str, "sections_found": dict,
                 "comparisons": list, "analysis_text": str, "conclusion_text": str,
                 "logic_consistency": str, "forbidden_words": list},
                ...
            ],
            "fto_opinion": str,
            "forbidden_words": list,
        }
    """
    if not isinstance(raw_text, str):
        return {"raw_output": "", "patent_analyses": [], "fto_opinion": "", "forbidden_words": []}

    result = {"raw_output": raw_text}

    # 종합 FTO 의견 추출
    fto_pat = re.compile(r"(?:◆|##)\s*종합\s*FTO\s*의견\s*◆?")
    fto_match = fto_pat.search(raw_text)
    if fto_match:
        result["fto_opinion"] = raw_text[fto_match.end():].strip()
        analysis_text = raw_text[:fto_match.start()]
    else:
        result["fto_opinion"] = ""
        analysis_text = raw_text

    # 특허별 섹션 분리 (## 특허 N: ... 패턴)
    patent_header = re.compile(r"##\s*특허\s*\d+\s*:\s*(.+)")
    splits = list(patent_header.finditer(analysis_text))

    patent_analyses = []
    for idx, match in enumerate(splits):
        start = match.end()
        end = splits[idx + 1].start() if idx + 1 < len(splits) else len(analysis_text)
        section_text = analysis_text[start:end].strip()
        patent_id = match.group(1).strip()

        parsed = parse_response(section_text)
        parsed["patent_id"] = patent_id
        patent_analyses.append(parsed)

    result["patent_analyses"] = patent_analyses
    result["forbidden_words"] = check_forbidden(raw_text)

    return result


def generate_fto(
    search_results: list[dict],
    user_query: str,
    verbose: bool = False,
    history: list[dict] = None,
) -> dict:
    """FTO 통합 분석. Top N을 한번에 GPT에 전달하여 선별 + 종합 의견 생성.

    Args:
        search_results: pipeline.search() 반환값.
        user_query: 사용자 원본 쿼리.
        verbose: 중간 로그 출력.
        history: 이전 대화 히스토리 [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        {
            "patent_analyses": list,  # 선별된 특허별 분석
            "fto_opinion": str,       # 종합 FTO 의견
            "raw_output": str,        # LLM 원문
            ...
        }
    """
    input_n = min(config.GENERATE_INPUT_N, len(search_results))

    if verbose:
        print(f"[FTO] 상위 {input_n}건 → GPT에 전달, {config.GENERATE_OUTPUT_N}건 선별 요청")
        for i, r in enumerate(search_results[:input_n]):
            pid = r.get("patent_id", "?")
            title = r.get("metadata", {}).get("invention_title", "")[:40]
            print(f"  [{i+1}] {pid} — {title}")

    messages = build_fto_prompt(search_results, user_query, history=history)

    if verbose:
        user_len = len(messages[1]["content"])
        print(f"[FTO] 프롬프트 길이: system={len(messages[0]['content'])}자, user={user_len}자")

    try:
        raw_output = call_llm(messages)
    except Exception as e:
        if verbose:
            print(f"[FTO] LLM 호출 실패: {e}")
        return {"error": str(e), "patent_analyses": [], "fto_opinion": "", "raw_output": ""}

    parsed = parse_fto_response(raw_output)

    if verbose:
        n_parsed = len(parsed.get("patent_analyses", []))
        print(f"[FTO] {n_parsed}건 분석 파싱 완료")
        for a in parsed.get("patent_analyses", []):
            print(f"  {a.get('patent_id', '?')} → {a.get('label', '?')}")
        if parsed.get("fto_opinion"):
            print(f"[FTO] 종합 의견: {parsed['fto_opinion'][:80]}...")

    return parsed
