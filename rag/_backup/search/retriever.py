"""리트리버: Dense/Sparse 검색 + RRF 점수 합산 + Patent Collapse.

하는 일:
    build/indexer.py가 빌드한 인덱스를 로드하여 검색합니다:
    1. dense_search(): KURE-v1 임베딩 → ChromaDB cosine 유사도 검색
    2. sparse_search(): kiwipiepy 토크나이징 → BM25 스코어링
    3. reciprocal_rank_fusion(): Dense+Sparse 순위를 가중합산
    4. patent_collapse(): 같은 특허의 여러 청크 중 최고 점수 1개만 남김

관계:
    - build/indexer.py가 만든 ChromaDB, bm25.pkl을 로드
    - build/tokenizer.py의 morpheme_tokenize()로 쿼리 토크나이징
    - pipeline.py가 이 파일의 4개 함수를 순서대로 호출
"""
import pickle

import chromadb
import numpy as np
from chromadb.config import Settings
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from .. import config
from ..build.tokenizer import morpheme_tokenize


# ══════════════════════════════════════════════════════
# Dense 검색 (KURE-v1 + ChromaDB)
# ══════════════════════════════════════════════════════

_model: SentenceTransformer | None = None
_collection: chromadb.Collection | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(config.EMBED_MODEL)
    return _model


def _get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(
            path=str(config.CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = client.get_or_create_collection(
            name=config.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def dense_search(query: str, top_k: int = None) -> list[tuple[str, float]]:
    """Dense 검색. 쿼리를 KURE-v1로 임베딩하여 ChromaDB에서 검색.

    Returns:
        [(chunk_id, distance), ...] distance 낮을수록 유사.
    """
    top_k = top_k or config.DENSE_TOP_K
    model = _get_model()
    col = _get_collection()

    query_embedding = model.encode([query])[0].tolist()
    results = col.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, col.count()),
    )

    pairs = []
    for cid, dist in zip(results["ids"][0], results["distances"][0]):
        pairs.append((cid, dist))
    return pairs


# ══════════════════════════════════════════════════════
# Sparse 검색 (BM25Okapi + kiwipiepy)
# ══════════════════════════════════════════════════════

_bm25: BM25Okapi | None = None
_chunk_ids: list[str] = []


def _load_bm25() -> tuple[BM25Okapi, list[str]]:
    global _bm25, _chunk_ids
    if _bm25 is None:
        data = pickle.loads(config.BM25_PATH.read_bytes())
        _bm25 = data["bm25"]
        _chunk_ids = data["chunk_ids"]
    return _bm25, _chunk_ids


def sparse_search(query: str, top_k: int = None) -> list[tuple[str, float]]:
    """BM25 검색. 쿼리를 kiwipiepy로 토크나이징하여 스코어링.

    Returns:
        [(chunk_id, score), ...] score 높을수록 관련.
    """
    top_k = top_k or config.BM25_TOP_K
    bm25, chunk_ids = _load_bm25()

    query_tokens = morpheme_tokenize(query)
    if not query_tokens:
        return []

    scores = bm25.get_scores(query_tokens)
    top_indices = np.argsort(scores)[::-1][:top_k]

    pairs = []
    for idx in top_indices:
        if scores[idx] > 0:
            pairs.append((chunk_ids[idx], float(scores[idx])))
    return pairs


# ══════════════════════════════════════════════════════
# RRF (Reciprocal Rank Fusion) + Patent Collapse
# ══════════════════════════════════════════════════════

def reciprocal_rank_fusion(
    dense_results: list[tuple[str, float]],
    sparse_results: list[tuple[str, float]],
    k: int = None,
    weights: tuple[float, float] = None,
) -> list[tuple[str, float]]:
    """Dense + Sparse 결과를 RRF로 합산."""
    k = k or config.RRF_K
    w_dense, w_sparse = weights or config.RRF_WEIGHTS

    dense_rank = {}
    for rank, (cid, _dist) in enumerate(
        sorted(dense_results, key=lambda x: x[1]), start=1
    ):
        if cid not in dense_rank:
            dense_rank[cid] = rank

    sparse_rank = {}
    for rank, (cid, _score) in enumerate(
        sorted(sparse_results, key=lambda x: x[1], reverse=True), start=1
    ):
        if cid not in sparse_rank:
            sparse_rank[cid] = rank

    all_ids = set(dense_rank.keys()) | set(sparse_rank.keys())
    max_dense = len(dense_results) + 1
    max_sparse = len(sparse_results) + 1

    rrf_scores = {}
    for cid in all_ids:
        d_rank = dense_rank.get(cid, max_dense)
        s_rank = sparse_rank.get(cid, max_sparse)
        rrf_scores[cid] = w_dense / (k + d_rank) + w_sparse / (k + s_rank)

    sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_results


def patent_collapse(
    rrf_results: list[tuple[str, float]],
    chunks_meta: dict[str, dict],
    top_k: int = None,
) -> list[dict]:
    """같은 특허의 여러 청크를 대표 1개로 축소."""
    top_k = top_k or config.FINAL_TOP_K

    best: dict[str, dict] = {}
    for cid, score in rrf_results:
        meta = chunks_meta.get(cid, {})
        patent_id = meta.get("apply_num", cid.split("_claim_")[0])

        if patent_id not in best or score > best[patent_id]["score"]:
            best[patent_id] = {
                "patent_id": patent_id,
                "score": score,
                "chunk_id": cid,
                "matched_claim_num": meta.get("indep_claim_num", 0),
                "metadata": meta,
            }

    collapsed = sorted(best.values(), key=lambda x: x["score"], reverse=True)
    return collapsed[:top_k]
