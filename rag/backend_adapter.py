"""백엔드 연동용 래퍼. 실제 FastAPI 연결은 백엔드 담당자가 수행.

사용법 (백엔드 담당자용):
    from rag.backend_adapter import analyze_product, search_only

    # 검색 + 분석
    result = analyze_product("헤스페리딘 포함 미백 화장품")

    # 검색만
    patents = search_only("헤스페리딘 포함 미백 화장품")
"""


def analyze_product(
    product_description: str,
    top_k: int = 10,
    verbose: bool = False,
    history: list[dict] = None,
) -> dict:
    """검색 + FTO 통합 분석. 백엔드 단일 진입점.

    Args:
        product_description: 사용자 제품 설명.
        top_k: 검색 결과 수.
        verbose: 중간 로그 출력.
        history: 이전 대화 히스토리 [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        {"query": str, "search_results": list, "fto_result": dict}
    """
    from .search.pipeline import analyze
    return analyze(
        product_description,
        top_k=top_k,
        verbose=verbose,
        history=history,
    )


def analyze_single_patent(
    search_result: dict,
    user_query: str,
    verbose: bool = False,
) -> dict:
    """단일 특허 sLLM 분석. 프론트엔드 개별 호출용.

    Args:
        search_result: search_only() 결과 리스트의 개별 항목.
        user_query: 사용자 제품 설명.
        verbose: 중간 로그 출력.

    Returns:
        parse_response() 결과 + patent_id, score, metadata 포함.
    """
    from .generate import build_prompt, call_llm, parse_response

    patent_id = search_result.get("patent_id", "unknown")
    if verbose:
        print(f"[G-single] {patent_id} 분석 시작")

    messages = build_prompt(search_result, user_query)
    raw_output = call_llm(messages)
    parsed = parse_response(raw_output)

    parsed["patent_id"] = patent_id
    parsed["score"] = search_result.get("score", 0)
    parsed["metadata"] = search_result.get("metadata", {})
    parsed["estoppel_claim_numbers"] = search_result.get("estoppel_claim_numbers", [])

    if verbose:
        print(f"[G-single] {patent_id} -> {parsed.get('label', '?')}")

    return parsed


def search_only(
    product_description: str,
    top_k: int = 10,
    verbose: bool = False,
) -> list[dict]:
    """검색만 수행 (sLLM 분석 없이).

    Args:
        product_description: 사용자 제품 설명.
        top_k: 검색 결과 수.
        verbose: 중간 로그 출력.

    Returns:
        검색 결과 리스트.
    """
    from .search.pipeline import search
    return search(product_description, top_k=top_k, verbose=verbose)
