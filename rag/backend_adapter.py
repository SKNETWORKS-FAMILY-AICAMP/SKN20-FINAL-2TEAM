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
) -> dict:
    """검색 + FTO 통합 분석. 백엔드 단일 진입점.

    Args:
        product_description: 사용자 제품 설명.
        top_k: 검색 결과 수.
        verbose: 중간 로그 출력.

    Returns:
        {"query": str, "search_results": list, "fto_result": dict}
    """
    from .search.pipeline import analyze
    return analyze(
        product_description,
        top_k=top_k,
        verbose=verbose,
    )


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
