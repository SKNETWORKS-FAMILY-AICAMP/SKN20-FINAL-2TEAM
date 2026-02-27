"""RAG 파이프라인 — GPT 전용 버전.

원본: pipeline.py
변경: generate_fto를 generate_gpt에서 임포트

search() 함수는 LLM을 사용하지 않으므로 원본 그대로 재사용.
"""
from .. import config
from .pipeline import search  # search()는 LLM 미사용 — 원본 그대로


def analyze(
    query: str,
    top_k: int = None,
    verbose: bool = False,
    **search_kwargs,
) -> dict:
    """전체 RAG+G 파이프라인. search() -> generate_fto() -> 최종 응답.

    GPT 버전: generate_gpt.generate_fto() 사용.
    """
    from ..generate_gpt import generate_fto  # ← GPT 버전

    search_results = search(query, top_k=top_k, verbose=verbose, **search_kwargs)

    if verbose:
        print(f"\n[FTO-GPT 분석 시작] 상위 {config.GENERATE_INPUT_N}건 → {config.GENERATE_OUTPUT_N}건 선별")

    fto_result = generate_fto(search_results, query, verbose=verbose)

    return {
        "query": query,
        "search_results": search_results,
        "fto_result": fto_result,
    }
