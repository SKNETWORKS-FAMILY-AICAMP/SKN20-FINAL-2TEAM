"""멀티쿼리: 사용자 쿼리에서 성분을 추출하고 검색 조합을 만듭니다.

하는 일:
    입력: "감국, 곰의말채, 애기닥나무를 포함한 미백용 화장품"
    → 성분 추출: ['감국', '곰의말채', '애기닥나무'], 맥락: ['미백', '화장품']
    → 쿼리 생성:
        1. 원본 쿼리
        2. "감국 미백 화장품", "곰의말채 미백 화장품", "애기닥나무 미백 화장품"
        3. "감국 곰의말채", "감국 애기닥나무", "곰의말채 애기닥나무"
        4. "감국 곰의말채 애기닥나무"

    성분 추출 방법 (config.MULTI_QUERY_MODE):
        - "rule":   regex 구조 기반 (기본값, 외부 의존 없음)
        - "llm":    GPT-4o-mini API 호출
        - "hybrid": regex 먼저, 실패 시 LLM fallback

주의 - 성분 추출에 kiwipiepy를 쓰면 안 됩니다:
    "곰의말채" → "곰","말","채"로 파괴됩니다.
    kiwipiepy는 build/tokenizer.py에서 BM25 토크나이징 전용입니다.

관계:
    - pipeline.py가 generate_queries()를 호출하여 멀티쿼리 리스트 생성
    - 생성된 쿼리들이 search/retriever.py의 dense_search(), sparse_search()에 전달
"""
import re
from itertools import combinations

from .. import config

# ── 성분 추출 패턴 ────────────────────────────────────

_END_MARKERS = re.compile(
    r'(?:을|를|로)\s*(?:포함|사용|함유|유효성분으로|접종|배합|혼합|첨가)'
)
_COMMA_SPLIT = re.compile(r'\s*,\s*')
_CONJ_SPLIT = re.compile(r'\s+(?:와|과|및|또는)\s+')

EFFECT_WORDS = {
    '미백', '주름', '보습', '항노화', '항산화', '치료', '개선', '예방',
    '진정', '피부', '자외선', '노화', '항균', '탈모', '여드름', '각질',
    '세정', '클렌징', '방부', '살균', '항염',
}
PRODUCT_WORDS = {
    '화장품', '크림', '로션', '세럼', '에센스', '팩', '마스크', '의약품',
    '식품', '제품', '액제', '조성물', '화장료', '샴푸', '린스', '토너',
}


def extract_components_rule(query: str) -> dict:
    """regex 구조 기반 성분 추출."""
    components = []
    context_words = []

    for w in EFFECT_WORDS:
        if w in query:
            context_words.append(w)
    for w in PRODUCT_WORDS:
        if w in query:
            context_words.append(w)

    matches = list(_END_MARKERS.finditer(query))
    if matches:
        prev_end = 0
        for m in matches:
            region = query[prev_end:m.start()].strip()
            if region:
                _extract_from_region(region, components)
            prev_end = m.end()
    else:
        _extract_from_region(query, components)
        all_keywords = EFFECT_WORDS | PRODUCT_WORDS
        components = [c for c in components if c not in all_keywords]

    seen = set()
    unique = []
    for c in components:
        c_clean = c.strip()
        if c_clean and c_clean not in seen and len(c_clean) >= 2:
            seen.add(c_clean)
            unique.append(c_clean)

    return {
        "components": unique,
        "context": list(set(context_words)),
        "method": "rule",
    }


def _extract_from_region(region: str, components: list):
    """성분 영역에서 개별 성분을 추출하여 components에 추가."""
    parts = _COMMA_SPLIT.split(region)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        sub_parts = _CONJ_SPLIT.split(part)
        for sp in sub_parts:
            sp = sp.strip()
            sp = re.sub(r'^(?:상기|그리고|더불어|특히)\s*', '', sp)
            if sp:
                components.append(sp)


def extract_components_llm(query: str) -> dict:
    """LLM 기반 성분 추출 (fallback). config.OPENAI_API_KEY 필요."""
    if not config.OPENAI_API_KEY:
        return {"components": [], "context": [], "synonyms": {}, "method": "llm_failed"}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)

        prompt = f"""사용자의 제품 설명에서 다음을 추출하세요:
1. 성분/구성요소 목록 (화학물질명, 재료명, 식물명 등 - 반드시 원문 그대로)
2. 제품 유형 (화장품, 의약품, 식품 등)
3. 효과/용도 (미백, 주름 완화, 치료 등)

제품 설명: {query}

JSON 형식으로만 출력 (다른 텍스트 없이):
{{"components": [...], "product_type": "...", "effects": [...]}}"""

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=500,
        )
        import json
        result = json.loads(resp.choices[0].message.content)

        context = []
        if result.get("product_type"):
            context.append(result["product_type"])
        context.extend(result.get("effects", []))

        return {
            "components": result.get("components", []),
            "context": context,
            "synonyms": result.get("synonyms", {}),
            "method": "llm",
        }
    except Exception as e:
        print(f"  [WARN] LLM 성분 추출 실패: {e}")
        return {"components": [], "context": [], "synonyms": {}, "method": "llm_failed"}


def extract_components(query: str) -> dict:
    """설정에 따른 성분 추출 디스패처."""
    mode = config.MULTI_QUERY_MODE

    if mode == "rule":
        return extract_components_rule(query)
    elif mode == "llm":
        return extract_components_llm(query)
    elif mode == "hybrid":
        result = extract_components_rule(query)
        if not result["components"]:
            result = extract_components_llm(query)
        return result
    else:
        return extract_components_rule(query)


def generate_queries(query: str) -> list[str]:
    """사용자 쿼리 → 멀티쿼리 리스트 생성."""
    extracted = extract_components(query)
    components = extracted["components"]
    context = extracted["context"]
    context_str = " ".join(context) if context else ""

    queries = [query]

    if not components:
        return queries

    for comp in components:
        q = f"{comp} {context_str}".strip()
        queries.append(q)

    if len(components) >= 2:
        for pair in combinations(components, 2):
            queries.append(" ".join(pair))

    if len(components) >= 2:
        queries.append(" ".join(components))

    seen = set()
    unique = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)

    return unique
