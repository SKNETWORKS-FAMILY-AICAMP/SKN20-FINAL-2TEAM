"""리트리버: Dense/Sparse 검색 + RRF 점수 합산 + Patent Collapse.

하는 일:
    1. dense_search(): KURE-v1 임베딩 -> ChromaDB cosine 유사도 검색
    2. sparse_search(): BM25 inverted index 기반 키워드 검색
    3. reciprocal_rank_fusion(): Dense+Sparse 순위를 가중합산
    4. patent_collapse(): 같은 특허의 여러 청크 중 최고 점수 1개만 남김

관계:
    - Dense: build/indexer.py가 만든 ChromaDB 로드
    - Sparse: build/build_sparse_index.py가 만든 bm25_index/ 로드
    - index/tokenizer.py의 morpheme_tokenize()로 쿼리 토크나이징
    - pipeline.py가 이 파일의 4개 함수를 순서대로 호출
"""
import json
import pickle

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

import importlib.util

from .. import config

# tokenizer.py는 index/ 폴더에 bm25.pkl과 함께 배포됨 (패키지가 아닌 데이터 폴더)
_tokenizer_path = config.INDEX_DIR / "tokenizer.py"
_spec = importlib.util.spec_from_file_location("tokenizer", _tokenizer_path)
_tokenizer_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tokenizer_mod)
morpheme_tokenize = _tokenizer_mod.morpheme_tokenize


# ══════════════════════════════════════════════════════
# Dense 검색 (KURE-v1 + ChromaDB)
# ══════════════════════════════════════════════════════

_model: SentenceTransformer | None = None
_collection: chromadb.Collection | None = None


def _get_model() -> SentenceTransformer:
    """KURE-v1 임베딩 모델 싱글톤. 최초 호출 시 1회 로드."""
    global _model
    if _model is None:
        _model = SentenceTransformer(config.EMBED_MODEL)
    return _model


def _get_collection() -> chromadb.Collection:
    """ChromaDB 컬렉션 싱글톤. cosine 거리 메트릭 사용."""
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


def dense_search(query: str, top_k: int = None, allowed_chunk_ids: list[str] = None) -> list[tuple[str, float, dict]]:
    """Dense 검색. 쿼리를 KURE-v1로 임베딩하여 ChromaDB에서 검색.

    Args:
        query: 검색 쿼리.
        top_k: 반환할 결과 수.
        allowed_chunk_ids: 사전필터링된 청크 ID 목록. None이면 전체 검색.

    Returns:
        [(chunk_id, distance, metadata), ...] distance 낮을수록 유사.
    """
    top_k = top_k or config.DENSE_TOP_K
    model = _get_model()
    col = _get_collection()

    # 쿼리를 1024차원 벡터로 임베딩
    query_embedding = model.encode([query])[0].tolist()

    # 사전필터링: allowed_chunk_ids가 있으면 해당 청크만 검색
    where_filter = None
    if allowed_chunk_ids is not None:
        where_filter = {"apply_num": {"$in": list(set(
            cid.split("_claim_")[0] for cid in allowed_chunk_ids
        ))}}

    n_results = min(top_k, col.count())

    # ChromaDB에서 cosine distance 기준 top-k 검색
    results = col.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["distances", "metadatas"],
        where=where_filter,
    )

    # (chunk_id, distance, metadata) 튜플 리스트로 변환
    pairs = []
    for cid, dist, meta in zip(results["ids"][0], results["distances"][0], results["metadatas"][0]):
        pairs.append((cid, dist, meta))
    return pairs


# ══════════════════════════════════════════════════════
# Sparse 검색 (BM25 inverted index)
# ══════════════════════════════════════════════════════

_sparse_index: dict | None = None


def _load_sparse_index() -> dict:
    """BM25 inverted index 로드. 최초 호출 시 1회."""
    global _sparse_index
    if _sparse_index is None:
        idx_dir = config.SPARSE_INDEX_DIR
        _sparse_index = {
            "postings": pickle.loads((idx_dir / "postings.pkl").read_bytes()),
            "idf": pickle.loads((idx_dir / "idf.pkl").read_bytes()),
            "doc_len": pickle.loads((idx_dir / "doc_len.pkl").read_bytes()),
            "doc_map": pickle.loads((idx_dir / "doc_map.pkl").read_bytes()),
        }
        with open(idx_dir / "meta.json", "r") as f:
            _sparse_index["meta"] = json.load(f)
        # chunk_id → doc_id 역방향 매핑 (사전필터링용)
        _sparse_index["reverse_doc_map"] = {v: k for k, v in _sparse_index["doc_map"].items()}
    return _sparse_index


def sparse_search(query: str, top_k: int = None, allowed_chunk_ids: list[str] = None) -> list[tuple[str, float]]:
    """Sparse 검색 (BM25).

    Args:
        query: 검색 쿼리.
        top_k: 반환할 결과 수.
        allowed_chunk_ids: 사전필터링된 청크 ID 목록. None이면 전체 검색.

    Returns:
        [(chunk_id, score), ...] score 높을수록 관련.
    """
    return _sparse_search_bm25(query, top_k, allowed_chunk_ids)


def _sparse_search_bm25(query: str, top_k: int = None, allowed_chunk_ids: list[str] = None) -> list[tuple[str, float]]:
    """BM25 검색. inverted index 기반 부분 접근.

    1. morpheme_tokenize(query) -> query_terms
    2. candidate_docs = union(postings[t] for t in query_terms)
    3. allowed_chunk_ids가 있으면 해당 doc_id만 허용 (사전필터링)
    4. candidate_docs에 대해서만 BM25 점수 계산
    5. 상위 top_k개 반환
    """
    top_k = top_k or config.BM25_TOP_K
    idx = _load_sparse_index()

    query_tokens = morpheme_tokenize(query)
    if not query_tokens:
        return []

    postings = idx["postings"]
    idf = idx["idf"]
    doc_len = idx["doc_len"]
    doc_map = idx["doc_map"]
    meta = idx["meta"]
    avg_dl = meta["avg_doc_len"]
    k1 = meta["k1"]
    b = meta["b"]

    # allowed_chunk_ids → allowed_doc_ids 변환 (사전필터링)
    allowed_doc_ids: set[int] | None = None
    if allowed_chunk_ids is not None:
        reverse_map = idx["reverse_doc_map"]
        allowed_doc_ids = {reverse_map[cid] for cid in allowed_chunk_ids if cid in reverse_map}

    # 후보 문서별 BM25 점수 누적 (쿼리 토큰이 포함된 문서만 접근)
    scores: dict[int, float] = {}

    for term in query_tokens:
        if term not in postings:
            continue
        term_idf = idf.get(term, 0.0)
        if term_idf <= 0:
            continue

        for doc_id, tf in postings[term]:
            if allowed_doc_ids is not None and doc_id not in allowed_doc_ids:
                continue
            dl = doc_len[doc_id]
            # BM25 Okapi: idf * tf * (k1+1) / (tf + k1 * (1 - b + b * dl/avgdl))
            tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
            scores[doc_id] = scores.get(doc_id, 0.0) + term_idf * tf_norm

    if not scores:
        return []

    sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [(doc_map[doc_id], score) for doc_id, score in sorted_docs]


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

    # Dense 결과를 distance 오름차순으로 순위 부여 (낮을수록 유사 = 높은 순위)
    dense_rank = {}
    for rank, (cid, _dist) in enumerate(
        sorted(dense_results, key=lambda x: x[1]), start=1
    ):
        if cid not in dense_rank:
            dense_rank[cid] = rank

    # Sparse 결과를 score 내림차순으로 순위 부여 (높을수록 관련 = 높은 순위)
    sparse_rank = {}
    for rank, (cid, _score) in enumerate(
        sorted(sparse_results, key=lambda x: x[1], reverse=True), start=1
    ):
        if cid not in sparse_rank:
            sparse_rank[cid] = rank

    # Dense와 Sparse 양쪽에 나타난 모든 chunk_id 합집합
    all_ids = set(dense_rank.keys()) | set(sparse_rank.keys())
    # 한쪽에만 있는 chunk는 최하위 순위 부여 (페널티)
    max_dense = len(dense_results) + 1
    max_sparse = len(sparse_results) + 1

    # RRF 공식: score = w / (k + rank) — k는 순위 편향 완화 파라미터
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

    # 같은 특허의 여러 청크 중 최고 RRF 점수를 가진 것만 유지
    best: dict[str, dict] = {}
    for cid, score in rrf_results:
        meta = chunks_meta.get(cid, {})
        # chunk_id에서 출원번호 추출 (형식: {apply_num}_claim_{num})
        patent_id = meta.get("apply_num", cid.split("_claim_")[0])

        if patent_id not in best or score > best[patent_id]["score"]:
            best[patent_id] = {
                "patent_id": patent_id,
                "score": score,
                "chunk_id": cid,
                "matched_claim_num": meta.get("indep_claim_num", 0),
                "metadata": meta,
            }

    # 점수 내림차순 정렬 후 top_k개 반환
    collapsed = sorted(best.values(), key=lambda x: x["score"], reverse=True)
    return collapsed[:top_k]
