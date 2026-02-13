"""RAG 모듈.

사용법:
    # 검색
    from rag import search
    results = search("헤스페리딘이 포함된 화장료")

    # 간단한 검색 (MySQL 필터 없이)
    from rag import search_simple
    results = search_simple("헤스페리딘 화장료")

    # 인덱스 빌드
    from rag.indexer import build_index
    build_index()
"""
from .search import search, search_simple, set_db_session

__all__ = ["search", "search_simple", "set_db_session"]
