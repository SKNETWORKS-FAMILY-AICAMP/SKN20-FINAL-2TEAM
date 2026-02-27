"""백엔드 연동용 래퍼 — GPT 전용 버전.

원본: backend_adapter.py
변경: pipeline_gpt에서 임포트

사용법 (백엔드 담당자용):
    from rag.backend_adapter_gpt import analyze_product, search_only
    result = analyze_product("헤스페리딘 포함 미백 화장품")
"""


def analyze_product(
    product_description: str,
    top_k: int = 10,
    verbose: bool = False,
) -> dict:
    """검색 + FTO 통합 분석 (GPT 버전). 백엔드 단일 진입점."""
    from .search.pipeline_gpt import analyze  # ← GPT 버전
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
    """검색만 수행 (LLM 분석 없이)."""
    from .search.pipeline import search  # search()는 LLM 미사용 — 원본 그대로
    return search(product_description, top_k=top_k, verbose=verbose)
