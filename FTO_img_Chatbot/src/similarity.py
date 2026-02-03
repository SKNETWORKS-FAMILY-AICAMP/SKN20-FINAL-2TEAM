from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np


def l2_normalize_rows(x: np.ndarray) -> np.ndarray:
    """행 단위 L2 정규화."""
    denom = np.linalg.norm(x, axis=1, keepdims=True)
    denom = np.clip(denom, 1e-12, None)
    return x / denom


def cosine_scores(user_vec: np.ndarray, ref_mat: np.ndarray) -> np.ndarray:
    """
    코사인 유사도 계산.
    user_vec: (D,), ref_mat: (N, D) - 둘 다 정규화되어 있으면 dot product = cosine
    """
    return ref_mat @ user_vec


@dataclass(frozen=True)
class SimilarItem:
    reference_image_id: str
    cosine_similarity: float
    metadata: Dict[str, Any] | None
    document: Dict[str, Any] | None


def retrieve_similar(
    user_vec: np.ndarray,
    ref_ids: np.ndarray,
    ref_emb: np.ndarray,
    metadata_idx: Dict[str, Dict[str, Any]],
    documents_idx: Dict[str, Dict[str, Any]],
    top_k: int,
    min_similarity: float,
    assume_ref_normalized: bool = True,
) -> List[SimilarItem]:
    """
    유사 이미지 검색.
    Returns: min_similarity 이상인 상위 top_k개 SimilarItem 리스트
    """
    if not assume_ref_normalized:
        ref_emb = l2_normalize_rows(ref_emb)

    # 유저 벡터 정규화
    user_vec = user_vec.astype(np.float32, copy=False)
    user_vec = user_vec / (np.linalg.norm(user_vec) + 1e-12)

    # 유사도 계산 및 정렬
    scores = cosine_scores(user_vec, ref_emb)
    order = np.argsort(-scores)

    results: List[SimilarItem] = []
    for idx in order[:max(top_k, 1)]:
        sid = str(ref_ids[idx])
        score = float(scores[idx])

        if score < min_similarity:
            continue

        results.append(
            SimilarItem(
                reference_image_id=sid,
                cosine_similarity=score,
                metadata=metadata_idx.get(sid),
                document=documents_idx.get(sid),
            )
        )

    return results