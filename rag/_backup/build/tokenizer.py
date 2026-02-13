"""kiwipiepy 형태소 분석기 래퍼. BM25 토크나이징 전용.

역할:
    - 텍스트에서 명사/외래어(NNG, NNP, SL)만 추출
    - indexer.py의 BM25 인덱싱 시 토크나이징
    - chunker.py의 sparse_text 생성 시 키워드 추출

주의 - 성분 추출에는 절대 사용하지 말 것:
    도메인 특수 용어를 형태소 단위로 파괴합니다.
    예) "곰의말채" → "곰","말","채"  /  "잔나비불로초" → "나비","불로초"
    성분 추출은 search/multi_query.py의 regex 또는 LLM으로 해야 합니다.

사용처: build/chunker.py, build/indexer.py, search/retriever.py
"""
import re
from functools import lru_cache

from kiwipiepy import Kiwi

from .. import config

_kiwi: Kiwi | None = None


def _get_kiwi() -> Kiwi:
    global _kiwi
    if _kiwi is None:
        _kiwi = Kiwi()
    return _kiwi


def morpheme_tokenize(text: str) -> list[str]:
    """BM25용 형태소 토크나이징. NNG/NNP/SL만 추출."""
    kiwi = _get_kiwi()
    tokens = kiwi.tokenize(text)
    return [
        tok.form
        for tok in tokens
        if tok.tag in config.KIWI_TARGET_TAGS and len(tok.form) >= 2
    ]


def extract_keywords_for_sparse(text: str) -> str:
    """sparse_text 생성용. 법률 상용구 제거 → 형태소 추출 → 공백 연결."""
    # 1. 법률 상용구 제거
    cleaned = text
    for stopword in config.SPARSE_LEGAL_STOPWORDS:
        cleaned = cleaned.replace(stopword, " ")

    # 2. "제N항" 패턴 추가 제거
    cleaned = re.sub(r"제\s*\d+\s*항", " ", cleaned)

    # 3. 숫자/범위 제거
    if config.SPARSE_REMOVE_NUMBERS:
        cleaned = re.sub(r"\d+[\.\,]?\d*\s*~\s*\d+[\.\,]?\d*", " ", cleaned)
        cleaned = re.sub(r"\d+[\.\,]?\d*\s*(?:중량%|wt%|%|℃|kg|cm|mm)", " ", cleaned)

    # 4. 형태소 추출
    tokens = morpheme_tokenize(cleaned)

    # 5. 중복 제거 (순서 유지)
    seen = set()
    unique = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    return " ".join(unique)
